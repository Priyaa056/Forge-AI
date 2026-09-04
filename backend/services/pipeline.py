"""Pipeline Orchestration Engine for FORGE AI Multi-Agent System."""

import os
import json
import uuid
import time
import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from pydantic import BaseModel, Field

from backend.schemas.pm_schema import PMOutput
from backend.schemas.ui_schema import UIOutput, PageComponentSpec, UIComponentSpec
from backend.schemas.backend_schema import BackendOutput, EndpointSpec, ResponseSchemaSpec, ServiceLayerSpec
from backend.schemas.db_schema import DBOutput, AlembicMetadata
from backend.schemas.auth_schema import AuthOutput, PasswordSecuritySpec, JWTStrategySpec
from backend.schemas.qa_schema import QAOutput
from backend.schemas.deploy_schema import DeployOutput
from backend.artifacts.artifact_schema import ArtifactStatus
from backend.artifacts.artifact_manager import ArtifactManager
from backend.artifacts.artifact_store import LocalJsonArtifactStore
from backend.artifacts.artifact_context import ArtifactContext
from backend.artifacts.rollback_manager import RollbackManager, RollbackResult
from backend.monitoring.logger import PipelineLogger, sanitize_secret
from backend.monitoring.execution_event import EventType, ExecutionEvent
from backend.agents.ui_agent import UIAgent
from backend.agents.backend_agent import BackendAgent
from backend.agents.db_agent import DBAgent
from backend.agents.auth_agent import AuthAgent
from backend.agents.qa_agent import QAAgent
from backend.agents.deploy_agent import DeployAgent

logger = logging.getLogger("forge_pipeline")



class AgentStatus(str, Enum):
    """Execution status for individual agents and overall pipeline."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


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
    PipelineStage.DEPLOY: [PipelineStage.PM, PipelineStage.UI, PipelineStage.BACKEND, PipelineStage.DB, PipelineStage.AUTH, PipelineStage.QA],
}


class PipelineExecutionState(BaseModel):
    """Data model representing current state of pipeline execution."""
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
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
    output_dir: str = Field(default="outputs")


class ForgePipeline:
    """Orchestrates 7-stage execution: PM -> UI -> Backend -> DB -> Auth -> QA -> Deploy."""

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
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if artifact_manager:
            self.artifact_manager = artifact_manager
        else:
            artifacts_dir = self.output_dir / "artifacts"
            self.artifact_manager = ArtifactManager(store=LocalJsonArtifactStore(storage_dir=str(artifacts_dir)))

        if pipeline_logger:
            self.pipeline_logger = pipeline_logger
        else:
            effective_log_dir = log_dir or str(self.output_dir / "logs")
            self.pipeline_logger = PipelineLogger(log_dir=effective_log_dir)

        self.monitoring_service = self.pipeline_logger.get_query_service()
        self.rollback_manager = RollbackManager(
            artifact_manager=self.artifact_manager,
            pipeline_logger=self.pipeline_logger,
        )


        self._agent_durations: Dict[str, float] = {}
        self._total_duration_ms: Optional[float] = None

        self.state = PipelineExecutionState(
            project_id=project_id or f"proj_{uuid.uuid4().hex[:8]}",
            run_id=run_id or f"run_{uuid.uuid4().hex[:8]}",
            user_prompt=user_prompt,
            output_dir=str(self.output_dir),
        )

        # Optional custom handler hooks (e.g. for plugging in actual agent implementations or mocks)
        self.agent_handlers: Dict[PipelineStage, Callable[[Dict[str, Any]], Dict[str, Any]]] = (
            agent_handlers or {}
        )

    def register_agent_handler(
        self,
        stage: PipelineStage,
        handler: Callable[[Dict[str, Any]], Dict[str, Any]]
    ):
        """Register a custom handler or agent runner for a specific stage."""
        self.agent_handlers[stage] = handler

    def execute_pm_stage(self) -> PMOutput:
        """Default PM stage implementation using existing pm_output.json or mock fallback."""
        pm_output_file = self.output_dir / "pm_output.json"

        if PipelineStage.PM in self.agent_handlers:
            raw_output = self.agent_handlers[PipelineStage.PM]({"user_prompt": self.state.user_prompt})
            pm_out = PMOutput.model_validate(raw_output)
        elif pm_output_file.exists():
            with open(pm_output_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            pm_out = PMOutput.model_validate(data)
        else:
            pm_out = PMOutput(
                project_name="TaskFlow",
                description=self.state.user_prompt or "Task management application",
                features=["User authentication", "Task CRUD operations"],
                tech_stack={"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
                database_entities=[]
            )

        with open(pm_output_file, "w", encoding="utf-8") as f:
            f.write(pm_out.model_dump_json(indent=2))

        return pm_out

    def execute_placeholder_stage(self, stage: PipelineStage) -> BaseModel:
        """Executes a placeholder/fallback runner for unbuilt agent stages."""
        pm_output = self.state.agent_outputs.get(PipelineStage.PM.value, {})
        project_name = pm_output.get("project_name", "GeneratedApp")

        if stage == PipelineStage.UI:
            data = UIOutput(
                project_name=project_name,
                framework="React",
                styling="Tailwind CSS",
                pages=[
                    PageComponentSpec(
                        name="Dashboard",
                        path="/",
                        components=["Navbar", "TaskCard"],
                        description="Main app dashboard"
                    )
                ],
                components=[
                    UIComponentSpec(
                        name="Navbar",
                        description="Navigation header",
                        props=[{"name": "title", "type": "string"}]
                    )
                ],
                design_system={"theme": "dark", "primaryColor": "#3b82f6"},
                routes=[{"path": "/", "component": "Dashboard"}]
            )
        elif stage == PipelineStage.BACKEND:
            data = BackendOutput(
                project_name=project_name,
                architecture="Clean Architecture (Controller-Service-Repository)",
                endpoints=[
                    EndpointSpec(
                        path="/api/health",
                        method="GET",
                        summary="Health check",
                        description="Check API status and connectivity",
                        operation_id="get_health",
                        tags=["Health"],
                        requires_auth=False,
                        required_roles=[],
                        request_schema=None,
                        response_schema=ResponseSchemaSpec(
                            name="HealthResponse",
                            status_code=200,
                            fields=[]
                        ),
                        parameters=[],
                        business_logic_summary="Returns server health status"
                    )
                ],
                service_layer=[
                    ServiceLayerSpec(
                        name="HealthService",
                        entity="System",
                        methods=[]
                    )
                ],
                repository_layer=[],
                global_dependencies=["get_db"],
                error_handlers=[]
            )
        elif stage == PipelineStage.DB:
            data = DBOutput(
                project_name=project_name,
                database_system="PostgreSQL",
                tables=[],
                sqlalchemy_models_code="# SQLAlchemy Models Placeholder",
                alembic_metadata=AlembicMetadata(
                    revision_id="init_001",
                    description="Initial migration schema",
                    upgrade_instructions=["op.create_table(...)"],
                    downgrade_instructions=["op.drop_table(...)"]
                )
            )
        elif stage == PipelineStage.AUTH:
            data = AuthOutput(
                project_name=project_name,
                password_security=PasswordSecuritySpec(),
                jwt_strategy=JWTStrategySpec(),
                auth_endpoints=[],
                rbac_roles=[]
            )
        elif stage == PipelineStage.QA:
            data = QAOutput(
                project_name=project_name,
                total_tests=5,
                passed_tests=5,
                failed_tests=0,
                coverage_percentage=100.0,
                lint_status="PASSED",
                security_scan_status="PASSED"
            )
        elif stage == PipelineStage.DEPLOY:
            data = DeployOutput(
                project_name=project_name,
                deployment_target="Docker",
                container_status="SUCCESS",
                health_check_status="HEALTHY"
            )
        else:
            raise ValueError(f"Unknown pipeline stage: {stage}")

        output_file = self.output_dir / f"{stage.value}_output.json"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=2))

        return data

    def run_stage(self, stage: PipelineStage) -> BaseModel:
        """Run single stage with status updates, artifact persistence, lineage tracking, timing, and error handling."""
        self.state.current_agent = stage
        self.state.agent_statuses[stage] = AgentStatus.RUNNING
        logger.info(f"Running pipeline stage: {stage.value}")

        stage_start = time.monotonic()
        self.pipeline_logger.log_agent_started(
            run_id=self.state.run_id,
            project_id=self.state.project_id,
            agent_name=stage.value,
            pipeline_stage=stage.value,
        )

        dep_stages = STAGE_LINEAGE_DEPENDENCIES.get(stage, [])
        input_artifact_ids = [
            self.state.artifact_ids[dep_stage.value]
            for dep_stage in dep_stages
            if dep_stage.value in self.state.artifact_ids
        ]

        artifact_context = ArtifactContext(
            artifact_manager=self.artifact_manager,
            project_id=self.state.project_id,
            run_id=self.state.run_id,
            current_agent=stage.value,
            user_prompt=self.state.user_prompt,
            input_artifact_ids=input_artifact_ids,
        )

        try:
            if stage in self.agent_handlers:
                context = {
                    "user_prompt": self.state.user_prompt,
                    "previous_outputs": self.state.agent_outputs,
                    "output_dir": str(self.output_dir),
                    "artifact_context": artifact_context,
                }
                raw_out = self.agent_handlers[stage](context)
                schema_cls = STAGE_SCHEMA_MAP[stage]
                validated_out = schema_cls.model_validate(raw_out)
            elif stage == PipelineStage.PM:
                validated_out = self.execute_pm_stage()
            elif stage == PipelineStage.UI:
                ui_agent = UIAgent(
                    pm_output_path=str(self.output_dir / "pm_output.json"),
                    backend_output_path=str(self.output_dir / "backend_output.json"),
                    output_filepath=str(self.output_dir / "ui_output.json"),
                    artifact_context=artifact_context,
                )
                validated_out = ui_agent.run()
            elif stage == PipelineStage.BACKEND:
                backend_agent = BackendAgent(
                    pm_output_path=str(self.output_dir / "pm_output.json"),
                    ui_output_path=str(self.output_dir / "ui_output.json"),
                    output_filepath=str(self.output_dir / "backend_output.json"),
                    artifact_context=artifact_context,
                )
                validated_out = backend_agent.run()
            elif stage == PipelineStage.DB:
                db_agent = DBAgent(
                    pm_output_path=str(self.output_dir / "pm_output.json"),
                    backend_output_path=str(self.output_dir / "backend_output.json"),
                    output_filepath=str(self.output_dir / "db_output.json"),
                    artifact_context=artifact_context,
                )
                validated_out = db_agent.run()
            elif stage == PipelineStage.AUTH:
                auth_agent = AuthAgent(
                    pm_output_path=str(self.output_dir / "pm_output.json"),
                    backend_output_path=str(self.output_dir / "backend_output.json"),
                    db_output_path=str(self.output_dir / "db_output.json"),
                    output_filepath=str(self.output_dir / "auth_output.json"),
                    artifact_context=artifact_context,
                )
                validated_out = auth_agent.run()
            elif stage == PipelineStage.QA:
                qa_agent = QAAgent(
                    pm_output_path=str(self.output_dir / "pm_output.json"),
                    backend_output_path=str(self.output_dir / "backend_output.json"),
                    db_output_path=str(self.output_dir / "db_output.json"),
                    auth_output_path=str(self.output_dir / "auth_output.json"),
                    ui_output_path=str(self.output_dir / "ui_output.json"),
                    output_filepath=str(self.output_dir / "qa_output.json"),
                    artifact_context=artifact_context,
                )
                validated_out = qa_agent.run()
            elif stage == PipelineStage.DEPLOY:
                deploy_agent = DeployAgent(
                    pm_output_path=str(self.output_dir / "pm_output.json"),
                    backend_output_path=str(self.output_dir / "backend_output.json"),
                    db_output_path=str(self.output_dir / "db_output.json"),
                    auth_output_path=str(self.output_dir / "auth_output.json"),
                    ui_output_path=str(self.output_dir / "ui_output.json"),
                    qa_output_path=str(self.output_dir / "qa_output.json"),
                    output_filepath=str(self.output_dir / "deploy_output.json"),
                    artifact_context=artifact_context,
                )
                validated_out = deploy_agent.run()
            else:
                validated_out = self.execute_placeholder_stage(stage)


            self.state.agent_outputs[stage.value] = validated_out.model_dump()
            self.state.agent_statuses[stage] = AgentStatus.COMPLETED

            stage_path = self.output_dir / f"{stage.value}_output.json"
            with open(stage_path, "w", encoding="utf-8") as f:
                f.write(validated_out.model_dump_json(indent=2))

            # Create persistent artifact
            artifact = self.artifact_manager.create_artifact(
                project_id=self.state.project_id,
                run_id=self.state.run_id,
                agent_name=stage.value,
                artifact_type=STAGE_SCHEMA_MAP[stage].__name__,
                content=validated_out,
                input_artifacts=input_artifact_ids,
                status=ArtifactStatus.COMPLETED,
                metadata={"user_prompt": self.state.user_prompt},
                schema_cls=STAGE_SCHEMA_MAP[stage],
            )
            self.state.artifact_ids[stage.value] = artifact.artifact_id

            duration_ms = round((time.monotonic() - stage_start) * 1000, 2)
            self._agent_durations[stage.value] = duration_ms

            self.pipeline_logger.log_artifact_created(
                run_id=self.state.run_id,
                project_id=self.state.project_id,
                agent_name=stage.value,
                pipeline_stage=stage.value,
                artifact_id=artifact.artifact_id,
                input_artifact_ids=input_artifact_ids,
            )

            self.pipeline_logger.log_agent_completed(
                run_id=self.state.run_id,
                project_id=self.state.project_id,
                agent_name=stage.value,
                pipeline_stage=stage.value,
                duration_ms=duration_ms,
                artifact_id=artifact.artifact_id,
                input_artifact_ids=input_artifact_ids,
            )

            return validated_out

        except Exception as e:
            duration_ms = round((time.monotonic() - stage_start) * 1000, 2)
            self._agent_durations[stage.value] = duration_ms

            self.state.agent_statuses[stage] = AgentStatus.FAILED
            self.state.error_reports[stage.value] = str(e)
            self.state.execution_status = AgentStatus.FAILED
            logger.error(f"Error in pipeline stage {stage.value}: {e}")

            failed_artifact_id = None
            # Persist FAILED artifact
            try:
                failed_artifact = self.artifact_manager.create_artifact(
                    project_id=self.state.project_id,
                    run_id=self.state.run_id,
                    agent_name=stage.value,
                    artifact_type=STAGE_SCHEMA_MAP[stage].__name__,
                    content={"error": sanitize_secret(str(e)), "stage": stage.value},
                    input_artifacts=input_artifact_ids,
                    status=ArtifactStatus.FAILED,
                    metadata={"error_type": type(e).__name__},
                )
                failed_artifact_id = failed_artifact.artifact_id
                self.state.artifact_ids[stage.value] = failed_artifact_id
            except Exception as artifact_err:
                logger.error(f"Failed to record FAILED artifact: {artifact_err}")

            self.pipeline_logger.log_artifact_failed(
                run_id=self.state.run_id,
                project_id=self.state.project_id,
                agent_name=stage.value,
                pipeline_stage=stage.value,
                artifact_id=failed_artifact_id,
                input_artifact_ids=input_artifact_ids,
                error_type=type(e).__name__,
                error_message=str(e),
            )

            self.pipeline_logger.log_agent_failed(
                run_id=self.state.run_id,
                project_id=self.state.project_id,
                agent_name=stage.value,
                pipeline_stage=stage.value,
                duration_ms=duration_ms,
                error_type=type(e).__name__,
                error_message=str(e),
                artifact_id=failed_artifact_id,
                input_artifact_ids=input_artifact_ids,
            )

            raise e

    def retry_stage(self, stage: PipelineStage) -> BaseModel:
        """Retry a failed stage."""
        logger.info(f"Retrying pipeline stage: {stage.value}")
        self.state.agent_statuses[stage] = AgentStatus.RETRYING
        if stage.value in self.state.error_reports:
            del self.state.error_reports[stage.value]
        return self.run_stage(stage)

    def rollback_stage(
        self,
        stage: PipelineStage,
        target_version: int,
        reason: Optional[str] = None,
        force: bool = False,
    ) -> RollbackResult:
        """Roll back a stage's artifact to a target version without destroying history."""
        logger.info(f"Rolling back stage '{stage.value}' to version {target_version}")
        schema_cls = STAGE_SCHEMA_MAP.get(stage)
        result = self.rollback_manager.rollback_to_version(
            project_id=self.state.project_id,
            agent_name=stage.value,
            target_version=target_version,
            run_id=self.state.run_id,
            reason=reason,
            force=force,
            schema_cls=schema_cls,
        )

        if result.status == "COMPLETED" and result.restored_artifact_id:
            self.state.artifact_ids[stage.value] = result.restored_artifact_id
            restored_art = self.artifact_manager.get_artifact(result.restored_artifact_id)
            if restored_art and restored_art.content:
                self.state.agent_outputs[stage.value] = restored_art.content
            self.state.agent_statuses[stage] = AgentStatus.COMPLETED
            if stage.value in self.state.error_reports:
                del self.state.error_reports[stage.value]

        return result

    def run_pipeline(self) -> PipelineExecutionState:
        """Execute full PM -> UI -> Backend -> DB -> Auth -> QA -> Deploy pipeline."""
        pipeline_start = time.monotonic()
        self.state.execution_status = AgentStatus.RUNNING

        self.pipeline_logger.log_pipeline_started(
            run_id=self.state.run_id,
            project_id=self.state.project_id,
        )

        for stage in STAGE_ORDER:
            try:
                self.run_stage(stage)
            except Exception as e:
                duration_ms = round((time.monotonic() - pipeline_start) * 1000, 2)
                self._total_duration_ms = duration_ms
                self.state.execution_status = AgentStatus.FAILED
                self.state.current_agent = stage

                self.pipeline_logger.log_pipeline_failed(
                    run_id=self.state.run_id,
                    project_id=self.state.project_id,
                    duration_ms=duration_ms,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                return self.state

        duration_ms = round((time.monotonic() - pipeline_start) * 1000, 2)
        self._total_duration_ms = duration_ms
        self.state.execution_status = AgentStatus.COMPLETED
        self.state.current_agent = None

        self.pipeline_logger.log_pipeline_completed(
            run_id=self.state.run_id,
            project_id=self.state.project_id,
            duration_ms=duration_ms,
        )
        return self.state

    def get_status_summary(self) -> Dict[str, Any]:
        """Returns JSON dashboard summary of current pipeline execution state."""
        completed_stages = [
            stage.value for stage, status in self.state.agent_statuses.items()
            if status == AgentStatus.COMPLETED
        ]
        failed_stages = [
            stage.value for stage, status in self.state.agent_statuses.items()
            if status == AgentStatus.FAILED
        ]

        agent_summaries: Dict[str, Any] = {}
        for stage in STAGE_ORDER:
            s_val = stage.value
            status = self.state.agent_statuses.get(stage, AgentStatus.PENDING).value
            duration = self._agent_durations.get(s_val, None)
            art_id = self.state.artifact_ids.get(s_val, None)
            err = self.state.error_reports.get(s_val, None)

            entry: Dict[str, Any] = {
                "status": status,
                "duration_ms": duration,
                "artifact_id": art_id,
            }
            if err:
                entry["error"] = sanitize_secret(err)
            agent_summaries[s_val] = entry

        if self._total_duration_ms is not None:
            total_duration = self._total_duration_ms
        else:
            durations = [d for d in self._agent_durations.values() if d is not None]
            total_duration = round(sum(durations), 2) if durations else 0.0

        events = self.pipeline_logger.get_events(run_id=self.state.run_id)
        latest_evt = events[-1] if events else None
        latest_event_type = latest_evt.event_type.value if latest_evt else None
        latest_event_timestamp = latest_evt.timestamp if latest_evt else None

        return {
            "project_id": self.state.project_id,
            "run_id": self.state.run_id,
            "user_prompt": sanitize_secret(self.state.user_prompt),
            "execution_status": self.state.execution_status.value,
            "current_agent": self.state.current_agent.value if self.state.current_agent else None,
            "agent_statuses": {
                stage.value: status.value for stage, status in self.state.agent_statuses.items()
            },
            "artifact_ids": self.state.artifact_ids,
            "error_reports": {k: sanitize_secret(v) for k, v in self.state.error_reports.items()} if self.state.error_reports else {},
            "completed_stages": completed_stages,
            "output_directory": str(self.output_dir),
            "total_duration_ms": total_duration,
            "successful_agent_count": len(completed_stages),
            "failed_agent_count": len(failed_stages),
            "artifact_count": len(self.state.artifact_ids),
            "failed_artifact_count": len(failed_stages),
            "latest_event_type": latest_event_type,
            "latest_event_timestamp": latest_event_timestamp,
            "monitoring_status": "ACTIVE",
            "monitoring status": "ACTIVE",
            "agents": agent_summaries,
            "agent_execution_summaries": agent_summaries,
        }
