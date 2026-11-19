"""Pipeline Orchestration Engine for the FORGE AI multi-agent system.

PM -> UI -> Backend -> DB -> Auth -> QA -> Deploy

* Each stage runs a specialised agent that consumes the validated artifacts of its upstream stages
  **from the current run only** (no stale outputs) and produces a versioned artifact plus the
  project files it owns.
* Every state change is emitted as a structured event (monitoring) and reported through the
  ``on_update`` callback so callers can persist/stream progress while the run executes.
* A failed stage stops the pipeline; downstream stages are marked SKIPPED; the run is FAILED.
  Transient failures are retried once (status RETRYING).
* QA and Deploy have success gates: a QA report with failing tests fails the QA stage even though
  the report itself is stored (as a FAILED artifact) for inspection.
"""

import json
import logging
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.agents.auth_agent import AuthAgent
from backend.agents.backend_agent import BackendAgent
from backend.agents.db_agent import DBAgent
from backend.agents.deploy_agent import DeployAgent
from backend.agents.pm_agent import PMAgent
from backend.agents.pm_analysis import PromptValidationError
from backend.agents.qa_agent import QAAgent
from backend.agents.ui_agent import UIAgent
from backend.artifacts.artifact_context import ArtifactContext
from backend.artifacts.artifact_manager import ArtifactManager
from backend.artifacts.artifact_schema import ArtifactStatus
from backend.artifacts.artifact_store import LocalJsonArtifactStore
from backend.artifacts.rollback_manager import RollbackManager, RollbackResult
from backend.codegen.project_files import GeneratedProject
from backend.exceptions import ValidationError as ContractValidationError
from backend.monitoring.logger import PipelineLogger, sanitize_secret
from backend.schemas.auth_schema import AuthOutput
from backend.schemas.backend_schema import BackendOutput
from backend.schemas.db_schema import DBOutput
from backend.schemas.deploy_schema import DeployOutput
from backend.schemas.pm_schema import PMOutput
from backend.schemas.qa_schema import QAOutput
from backend.schemas.ui_schema import UIOutput

logger = logging.getLogger("forge_pipeline")


class AgentStatus(str, Enum):
    """Execution status for individual agents and the overall pipeline."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    SKIPPED = "SKIPPED"


class PipelineStage(str, Enum):
    """Pipeline agent stages in execution order."""
    PM = "pm"
    UI = "ui"
    BACKEND = "backend"
    DB = "db"
    AUTH = "auth"
    QA = "qa"
    DEPLOY = "deploy"


STAGE_ORDER = [
    PipelineStage.PM,
    PipelineStage.UI,
    PipelineStage.BACKEND,
    PipelineStage.DB,
    PipelineStage.AUTH,
    PipelineStage.QA,
    PipelineStage.DEPLOY,
]

STAGE_SCHEMA_MAP = {
    PipelineStage.PM: PMOutput,
    PipelineStage.UI: UIOutput,
    PipelineStage.BACKEND: BackendOutput,
    PipelineStage.DB: DBOutput,
    PipelineStage.AUTH: AuthOutput,
    PipelineStage.QA: QAOutput,
    PipelineStage.DEPLOY: DeployOutput,
}

STAGE_LINEAGE_DEPENDENCIES = {
    PipelineStage.PM: [],
    PipelineStage.UI: [PipelineStage.PM],
    PipelineStage.BACKEND: [PipelineStage.PM, PipelineStage.UI],
    PipelineStage.DB: [PipelineStage.PM, PipelineStage.BACKEND],
    PipelineStage.AUTH: [PipelineStage.PM, PipelineStage.BACKEND, PipelineStage.DB],
    PipelineStage.QA: [PipelineStage.PM, PipelineStage.UI, PipelineStage.BACKEND, PipelineStage.DB, PipelineStage.AUTH],
    PipelineStage.DEPLOY: [PipelineStage.PM, PipelineStage.UI, PipelineStage.BACKEND, PipelineStage.DB,
                           PipelineStage.AUTH, PipelineStage.QA],
}

# Spec file written by each stage inside the run directory (``specs/``).
STAGE_SPEC_FILES = {
    PipelineStage.PM: "requirements.json",
    PipelineStage.UI: "ui_spec.json",
    PipelineStage.BACKEND: "api_spec.json",
    PipelineStage.DB: "database_schema.json",
    PipelineStage.AUTH: "auth_spec.json",
    PipelineStage.QA: "qa_report.json",
    PipelineStage.DEPLOY: "deployment_report.json",
}

STAGE_TITLES = {
    PipelineStage.PM: "Project Manager", PipelineStage.UI: "UI", PipelineStage.BACKEND: "Backend",
    PipelineStage.DB: "Database", PipelineStage.AUTH: "Authentication", PipelineStage.QA: "QA",
    PipelineStage.DEPLOY: "Deploy",
}

NON_RETRYABLE = (PromptValidationError, ContractValidationError)

# Success gates: a stage whose output reports failure fails the run even though the output is stored.
STAGE_GATES = {
    PipelineStage.QA: QAAgent.is_success,
    PipelineStage.DEPLOY: DeployAgent.is_success,
}


class StageGateFailed(Exception):
    """Raised when an agent ran to completion but its result does not meet the success gate (QA/Deploy)."""


class SimulatedAgentFailure(RuntimeError):
    """Fault injected on request (``simulate_failure``) to exercise failure handling and recovery."""


class PipelineExecutionState(BaseModel):
    """Data model representing the current state of a pipeline execution."""
    project_id: str = Field(default_factory=lambda: f"proj_{uuid.uuid4().hex[:8]}")
    run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:8]}")
    user_prompt: str = Field(default="", description="User application idea prompt")
    execution_status: AgentStatus = Field(default=AgentStatus.PENDING)
    current_agent: Optional[PipelineStage] = Field(default=None)
    agent_statuses: Dict[PipelineStage, AgentStatus] = Field(
        default_factory=lambda: {stage: AgentStatus.PENDING for stage in STAGE_ORDER}
    )
    agent_outputs: Dict[str, Any] = Field(default_factory=dict)
    artifact_ids: Dict[str, str] = Field(default_factory=dict)
    error_reports: Dict[str, str] = Field(default_factory=dict)
    agent_attempts: Dict[str, int] = Field(default_factory=dict)
    agent_modes: Dict[str, str] = Field(default_factory=dict)
    agent_files: Dict[str, List[str]] = Field(default_factory=dict)
    output_dir: str = Field(default="outputs")
    app_dir: Optional[str] = Field(default=None)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None


class ForgePipeline:
    """Orchestrates the 7-stage execution: PM -> UI -> Backend -> DB -> Auth -> QA -> Deploy."""

    def __init__(
        self,
        user_prompt: str = "",
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        output_dir: str = "outputs",
        agent_handlers: Optional[Dict[PipelineStage, Callable[[Dict[str, Any]], Dict[str, Any]]]] = None,
        artifact_manager: Optional[ArtifactManager] = None,
        pipeline_logger: Optional[PipelineLogger] = None,
        log_dir: Optional[str] = None,
        generate_code: bool = True,
        simulate_failure: Optional[str] = None,
        previous_requirements: Optional[Dict[str, Any]] = None,
        on_update: Optional[Callable[["ForgePipeline"], None]] = None,
        max_attempts: int = 2,
        qa_frontend_build: Optional[bool] = None,
        deploy_health_check: bool = True,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.specs_dir = self.output_dir / "specs"
        self.specs_dir.mkdir(parents=True, exist_ok=True)

        self.artifact_manager = artifact_manager or ArtifactManager(
            store=LocalJsonArtifactStore(storage_dir=str(self.output_dir / "artifacts")))
        self.pipeline_logger = pipeline_logger or PipelineLogger(log_dir=log_dir or str(self.output_dir / "logs"))
        self.monitoring_service = self.pipeline_logger.get_query_service()
        self.rollback_manager = RollbackManager(artifact_manager=self.artifact_manager, pipeline_logger=self.pipeline_logger)

        self.generate_code = generate_code
        self.project: Optional[GeneratedProject] = GeneratedProject(self.output_dir / "app") if generate_code else None
        self.simulate_failure = (simulate_failure or "").lower() or None
        self.previous_requirements = previous_requirements
        self.on_update = on_update
        self.max_attempts = max(1, max_attempts)
        self.qa_frontend_build = qa_frontend_build
        self.deploy_health_check = deploy_health_check

        self._agent_durations: Dict[str, float] = {}
        self._agent_started: Dict[str, float] = {}
        self._total_duration_ms: Optional[float] = None

        self.state = PipelineExecutionState(
            project_id=project_id or f"proj_{uuid.uuid4().hex[:8]}",
            run_id=run_id or f"run_{uuid.uuid4().hex[:8]}",
            user_prompt=user_prompt,
            output_dir=str(self.output_dir),
            app_dir=str(self.project.root) if self.project else None,
        )
        self.agent_handlers: Dict[PipelineStage, Callable[[Dict[str, Any]], Dict[str, Any]]] = agent_handlers or {}

    # ------------------------------------------------------------------ helpers
    def register_agent_handler(self, stage: PipelineStage, handler: Callable[[Dict[str, Any]], Dict[str, Any]]):
        """Register a custom handler for a stage (used by tests and extensions)."""
        self.agent_handlers[stage] = handler

    def _notify(self) -> None:
        if self.on_update:
            try:
                self.on_update(self)
            except Exception as exc:  # never let persistence break the run
                logger.warning("on_update callback failed: %s", exc)

    def _agent_logger(self, stage: PipelineStage) -> Callable[[str, str], None]:
        def log(message: str, level: str = "info") -> None:
            self.pipeline_logger.log_agent_message(self.state.run_id, self.state.project_id, stage.value, message, level)
        return log

    def _spec_path(self, stage: PipelineStage) -> Path:
        return self.specs_dir / STAGE_SPEC_FILES[stage]

    def _build_agent(self, stage: PipelineStage, context: ArtifactContext):
        common = {"artifact_context": context, "project": self.project, "log_fn": self._agent_logger(stage),
                  "output_filepath": str(self._spec_path(stage))}
        if stage == PipelineStage.PM:
            return PMAgent(user_prompt=self.state.user_prompt, previous_requirements=self.previous_requirements, **common)
        if stage == PipelineStage.UI:
            return UIAgent(**common)
        if stage == PipelineStage.BACKEND:
            return BackendAgent(**common)
        if stage == PipelineStage.DB:
            return DBAgent(**common)
        if stage == PipelineStage.AUTH:
            return AuthAgent(**common)
        if stage == PipelineStage.QA:
            return QAAgent(run_frontend_build=self.qa_frontend_build, **common)
        if stage == PipelineStage.DEPLOY:
            return DeployAgent(run_health_check=self.deploy_health_check, **common)
        raise ValueError(f"Unknown pipeline stage: {stage}")

    def _execute_agent(self, stage: PipelineStage, context: ArtifactContext, input_artifact_ids: List[str]):
        """Run one attempt of a stage. Returns (validated_output, metadata, succeeded_gate)."""
        if self.simulate_failure == stage.value:
            self._agent_logger(stage)("Fault injection requested for this stage (test mode)", "warning")
            raise SimulatedAgentFailure(f"Simulated failure injected into the {STAGE_TITLES[stage]} agent (test mode)")
        schema_cls = STAGE_SCHEMA_MAP[stage]
        if stage in self.agent_handlers:
            handler_context = {
                "user_prompt": self.state.user_prompt,
                "previous_outputs": self.state.agent_outputs,
                "output_dir": str(self.output_dir),
                "artifact_context": context,
                "project": self.project,
            }
            validated = schema_cls.model_validate(self.agent_handlers[stage](handler_context))
            self._spec_path(stage).write_text(validated.model_dump_json(indent=2), encoding="utf-8")
            gate = STAGE_GATES.get(stage)
            return (validated, {"generation_mode": "custom_handler", "generated_files": [], "notes": []},
                    gate(validated) if gate else True)
        agent = self._build_agent(stage, context)
        validated = agent.run()
        gate = STAGE_GATES.get(stage)
        succeeded = gate(validated) if gate else True
        return validated, agent.result_metadata(), succeeded

    # ------------------------------------------------------------------ stage execution
    def run_stage(self, stage: PipelineStage) -> BaseModel:
        """Run a single stage with status updates, retries, artifact persistence, lineage tracking and timing."""
        self.state.current_agent = stage
        self.state.agent_statuses[stage] = AgentStatus.RUNNING
        stage_start = time.monotonic()
        self._agent_started[stage.value] = time.time()
        self.pipeline_logger.log_agent_started(run_id=self.state.run_id, project_id=self.state.project_id,
                                               agent_name=stage.value, pipeline_stage=stage.value)
        self._notify()

        input_artifact_ids = [self.state.artifact_ids[d.value] for d in STAGE_LINEAGE_DEPENDENCIES.get(stage, [])
                              if d.value in self.state.artifact_ids]
        context = ArtifactContext(
            artifact_manager=self.artifact_manager, project_id=self.state.project_id, run_id=self.state.run_id,
            current_agent=stage.value, user_prompt=self.state.user_prompt, input_artifact_ids=input_artifact_ids,
            strict_run=True,
        )
        schema_cls = STAGE_SCHEMA_MAP[stage]
        attempt = 0
        while True:
            attempt += 1
            self.state.agent_attempts[stage.value] = attempt
            try:
                validated, metadata, succeeded = self._execute_agent(stage, context, input_artifact_ids)
                break
            except Exception as exc:  # noqa: BLE001 - every failure is recorded and reported
                retryable = not isinstance(exc, NON_RETRYABLE) and attempt < self.max_attempts
                if retryable:
                    self.state.agent_statuses[stage] = AgentStatus.RETRYING
                    self.pipeline_logger.log_agent_retrying(self.state.run_id, self.state.project_id, stage.value,
                                                            attempt, type(exc).__name__, sanitize_secret(str(exc)))
                    self._notify()
                    continue
                self._record_failure(stage, exc, input_artifact_ids, stage_start, content=None)
                raise

        output_dict = validated.model_dump()
        self.state.agent_outputs[stage.value] = output_dict
        self.state.agent_modes[stage.value] = metadata.get("generation_mode", "deterministic")
        self.state.agent_files[stage.value] = metadata.get("generated_files", [])
        if self.project is not None:
            self.project.save_manifest({"project_id": self.state.project_id, "run_id": self.state.run_id})

        if not succeeded:
            summary = output_dict.get("summary") or output_dict.get("next_step") or "success gate not met"
            exc = StageGateFailed(f"{STAGE_TITLES[stage]} agent reported failure: {summary}")
            self._record_failure(stage, exc, input_artifact_ids, stage_start, content=output_dict, metadata=metadata)
            raise exc

        try:
            artifact = self.artifact_manager.create_artifact(
                project_id=self.state.project_id, run_id=self.state.run_id, agent_name=stage.value,
                artifact_type=schema_cls.__name__, content=validated, input_artifacts=input_artifact_ids,
                status=ArtifactStatus.COMPLETED, schema_cls=schema_cls,
                metadata={**metadata, "attempts": attempt, "spec_file": STAGE_SPEC_FILES[stage],
                          "user_prompt": sanitize_secret(self.state.user_prompt)[:500]},
            )
        except Exception as exc:  # e.g. artifact validation / secret scanning rejected the output
            self._record_failure(stage, exc, input_artifact_ids, stage_start, content=None, metadata=metadata)
            raise
        self.state.artifact_ids[stage.value] = artifact.artifact_id
        self.state.agent_statuses[stage] = AgentStatus.COMPLETED
        duration_ms = round((time.monotonic() - stage_start) * 1000, 2)
        self._agent_durations[stage.value] = duration_ms
        self.pipeline_logger.log_artifact_created(
            run_id=self.state.run_id, project_id=self.state.project_id, agent_name=stage.value,
            pipeline_stage=stage.value, artifact_id=artifact.artifact_id, input_artifact_ids=input_artifact_ids)
        self.pipeline_logger.log_agent_completed(
            run_id=self.state.run_id, project_id=self.state.project_id, agent_name=stage.value,
            pipeline_stage=stage.value, duration_ms=duration_ms, artifact_id=artifact.artifact_id,
            input_artifact_ids=input_artifact_ids)
        self._notify()
        return validated

    def _record_failure(self, stage: PipelineStage, exc: Exception, input_artifact_ids: List[str], stage_start: float,
                        content: Optional[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None) -> None:
        duration_ms = round((time.monotonic() - stage_start) * 1000, 2)
        self._agent_durations[stage.value] = duration_ms
        clean_err = sanitize_secret(str(exc))
        self.state.agent_statuses[stage] = AgentStatus.FAILED
        self.state.error_reports[stage.value] = clean_err
        self.state.execution_status = AgentStatus.FAILED
        logger.error("Error in pipeline stage %s: %s", stage.value, clean_err)
        failed_artifact_id = None
        try:
            failed = self.artifact_manager.create_artifact(
                project_id=self.state.project_id, run_id=self.state.run_id, agent_name=stage.value,
                artifact_type=STAGE_SCHEMA_MAP[stage].__name__,
                content=content if content is not None else {"error": clean_err, "stage": stage.value},
                input_artifacts=input_artifact_ids, status=ArtifactStatus.FAILED,
                metadata={**(metadata or {}), "error_type": type(exc).__name__, "error": clean_err[:2000]},
            )
            failed_artifact_id = failed.artifact_id
            self.state.artifact_ids[stage.value] = failed_artifact_id
        except Exception as artifact_err:
            logger.error("Failed to record FAILED artifact: %s", artifact_err)
        self.pipeline_logger.log_artifact_failed(
            run_id=self.state.run_id, project_id=self.state.project_id, agent_name=stage.value,
            pipeline_stage=stage.value, artifact_id=failed_artifact_id, input_artifact_ids=input_artifact_ids,
            error_type=type(exc).__name__, error_message=clean_err)
        self.pipeline_logger.log_agent_failed(
            run_id=self.state.run_id, project_id=self.state.project_id, agent_name=stage.value,
            pipeline_stage=stage.value, duration_ms=duration_ms, error_type=type(exc).__name__,
            error_message=clean_err, artifact_id=failed_artifact_id, input_artifact_ids=input_artifact_ids)
        self._notify()

    def _run_corrections(self) -> bool:
        """Re-run the agents named in the QA report's correction tasks (one round per run)."""
        if getattr(self, "_corrections_done", False):
            return False
        tasks = (self.state.agent_outputs.get(PipelineStage.QA.value) or {}).get("correction_tasks") or []
        by_agent = {"UIAgent": PipelineStage.UI, "BackendAgent": PipelineStage.BACKEND, "DBAgent": PipelineStage.DB,
                    "AuthAgent": PipelineStage.AUTH}
        targets = {by_agent[t.get("agent")] for t in tasks if t.get("agent") in by_agent}
        if not targets:
            return False
        self._corrections_done = True
        log = self._agent_logger(PipelineStage.QA)
        for task in tasks:
            log(f"Correction task for {task.get('agent')}: " + "; ".join(task.get("issues", [])[:5]), "warning")
        for stage in STAGE_ORDER:  # dependants of a corrected stage are regenerated too
            if stage in targets or (stage in by_agent.values() and any(
                    t in STAGE_LINEAGE_DEPENDENCIES.get(stage, []) for t in targets)):
                targets.add(stage)
                self.run_stage(stage)
        self.state.error_reports.pop(PipelineStage.QA.value, None)
        return True

    def retry_stage(self, stage: PipelineStage) -> BaseModel:
        """Retry a failed stage."""
        self.state.agent_statuses[stage] = AgentStatus.RETRYING
        self.state.error_reports.pop(stage.value, None)
        return self.run_stage(stage)

    def rollback_stage(self, stage: PipelineStage, target_version: int, reason: Optional[str] = None,
                       force: bool = False) -> RollbackResult:
        """Roll back a single stage's artifact to a target version (artifact level, history preserved)."""
        result = self.rollback_manager.rollback_to_version(
            project_id=self.state.project_id, agent_name=stage.value, target_version=target_version,
            run_id=self.state.run_id, reason=reason, force=force, schema_cls=STAGE_SCHEMA_MAP.get(stage))
        if result.status == "COMPLETED" and result.restored_artifact_id:
            self.state.artifact_ids[stage.value] = result.restored_artifact_id
            restored = self.artifact_manager.get_artifact(result.restored_artifact_id)
            if restored and restored.content:
                self.state.agent_outputs[stage.value] = restored.content
            self.state.agent_statuses[stage] = AgentStatus.COMPLETED
            self.state.error_reports.pop(stage.value, None)
        return result

    def run_pipeline(self) -> PipelineExecutionState:
        """Execute the full PM -> UI -> Backend -> DB -> Auth -> QA -> Deploy pipeline."""
        pipeline_start = time.monotonic()
        self.state.started_at = time.time()
        self.state.execution_status = AgentStatus.RUNNING
        self.pipeline_logger.log_pipeline_started(run_id=self.state.run_id, project_id=self.state.project_id,
                                                  message=f"Pipeline started: {sanitize_secret(self.state.user_prompt)[:200]}")
        self._notify()
        for index, stage in enumerate(STAGE_ORDER):
            try:
                try:
                    self.run_stage(stage)
                except StageGateFailed:
                    # requirement-based QA: send targeted correction tasks to the responsible agents once,
                    # then verify again; the run fails if the requirements are still not implemented.
                    if stage != PipelineStage.QA or not self._run_corrections():
                        raise
                    self.run_stage(stage)
            except Exception as exc:  # noqa: BLE001
                for later in STAGE_ORDER[index + 1:]:
                    self.state.agent_statuses[later] = AgentStatus.SKIPPED
                    self.pipeline_logger.log_agent_skipped(self.state.run_id, self.state.project_id, later.value,
                                                           f"Skipped because the {STAGE_TITLES[stage]} agent failed")
                self._total_duration_ms = round((time.monotonic() - pipeline_start) * 1000, 2)
                self.state.execution_status = AgentStatus.FAILED
                self.state.current_agent = stage
                self.state.finished_at = time.time()
                self.pipeline_logger.log_pipeline_failed(
                    run_id=self.state.run_id, project_id=self.state.project_id, duration_ms=self._total_duration_ms,
                    error_type=type(exc).__name__, error_message=sanitize_secret(str(exc)))
                self._notify()
                return self.state
        self._total_duration_ms = round((time.monotonic() - pipeline_start) * 1000, 2)
        self.state.execution_status = AgentStatus.COMPLETED
        self.state.current_agent = None
        self.state.finished_at = time.time()
        self.pipeline_logger.log_pipeline_completed(run_id=self.state.run_id, project_id=self.state.project_id,
                                                    duration_ms=self._total_duration_ms)
        self._notify()
        return self.state

    # ------------------------------------------------------------------ reporting
    def get_status_summary(self) -> Dict[str, Any]:
        """JSON summary of the current execution state for the dashboard."""
        statuses = self.state.agent_statuses
        completed = [s.value for s, st in statuses.items() if st == AgentStatus.COMPLETED]
        failed = [s.value for s, st in statuses.items() if st == AgentStatus.FAILED]
        finished = sum(1 for st in statuses.values() if st in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.SKIPPED))
        agents: Dict[str, Any] = {}
        for stage in STAGE_ORDER:
            value = stage.value
            running_for = None
            if statuses[stage] in (AgentStatus.RUNNING, AgentStatus.RETRYING) and value in self._agent_started:
                running_for = round((time.time() - self._agent_started[value]) * 1000, 0)
            entry: Dict[str, Any] = {
                "title": STAGE_TITLES[stage],
                "status": statuses[stage].value,
                "duration_ms": self._agent_durations.get(value, running_for),
                "artifact_id": self.state.artifact_ids.get(value),
                "attempts": self.state.agent_attempts.get(value, 0),
                "generation_mode": self.state.agent_modes.get(value),
                "generated_files": len(self.state.agent_files.get(value, [])),
                "spec_file": STAGE_SPEC_FILES[stage],
            }
            if value in self.state.error_reports:
                entry["error"] = sanitize_secret(self.state.error_reports[value])
            agents[value] = entry
        if self._total_duration_ms is not None:
            total = self._total_duration_ms
        elif self.state.started_at:
            total = round((time.time() - self.state.started_at) * 1000, 2)
        else:
            total = 0.0
        events = self.pipeline_logger.get_events(run_id=self.state.run_id)
        latest = events[-1] if events else None
        qa = self.state.agent_outputs.get("qa") or {}
        deploy = self.state.agent_outputs.get("deploy") or {}
        return {
            "project_id": self.state.project_id,
            "run_id": self.state.run_id,
            "user_prompt": sanitize_secret(self.state.user_prompt),
            "execution_status": self.state.execution_status.value,
            "current_agent": self.state.current_agent.value if self.state.current_agent else None,
            "progress_percent": round(100 * finished / len(STAGE_ORDER)),
            "agent_statuses": {s.value: st.value for s, st in statuses.items()},
            "artifact_ids": dict(self.state.artifact_ids),
            "error_reports": {k: sanitize_secret(v) for k, v in self.state.error_reports.items()},
            "completed_stages": completed,
            "output_directory": str(self.output_dir),
            "app_directory": self.state.app_dir,
            "total_duration_ms": total,
            "successful_agent_count": len(completed),
            "failed_agent_count": len(failed),
            "artifact_count": len(self.state.artifact_ids),
            "failed_artifact_count": len(failed),
            "latest_event_type": latest.event_type.value if latest else None,
            "latest_event_timestamp": latest.timestamp if latest else None,
            "monitoring_status": "ACTIVE",
            "simulated_failure": self.simulate_failure,
            "qa_summary": {k: qa.get(k) for k in ("status", "tests_run", "tests_passed", "tests_failed", "score",
                                                     "frontend_build", "summary")} if qa else None,
            "deployment_summary": {k: deploy.get(k) for k in ("status", "deployment_ready", "docker_available")} if deploy else None,
            "agents": agents,
            "agent_execution_summaries": agents,
        }

    def write_run_summary(self, path: Optional[Path] = None) -> Path:
        path = path or (self.output_dir / "run_summary.json")
        path.write_text(json.dumps(self.get_status_summary(), indent=2, default=str), encoding="utf-8")
        return path
