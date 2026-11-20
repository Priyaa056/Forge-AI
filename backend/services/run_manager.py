"""Background execution of pipeline runs with live, persisted progress."""

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from backend.artifacts.artifact_manager import ArtifactManager
from backend.artifacts.artifact_store import LocalJsonArtifactStore
from backend.codegen.project_files import verify_manifest
from backend.config import env_int, workspace_dir
from backend.monitoring.logger import PipelineLogger
from backend.services.pipeline import AgentStatus, ForgePipeline
from backend.services.project_store import ProjectBusy, ProjectStore


class RefinementUnavailable(ValueError):
    """The project cannot be refined right now (no live version, or its files failed verification)."""

logger = logging.getLogger("forge.runs")


class RunManager:
    def __init__(self, store: Optional[ProjectStore] = None):
        ws = workspace_dir()
        self.store = store or ProjectStore()
        self.artifact_manager = ArtifactManager(store=LocalJsonArtifactStore(storage_dir=str(ws / "artifacts")))
        self.pipeline_logger = PipelineLogger(log_dir=str(ws / "logs"))
        self.active: Dict[str, ForgePipeline] = {}
        self.promotion: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=env_int("FORGE_MAX_CONCURRENT_RUNS", 2), thread_name_prefix="forge-run")
        self.on_promoted = None  # callback(project_id) e.g. to refresh a running preview

    def _summary(self, pipeline: ForgePipeline) -> Dict[str, Any]:
        summary = pipeline.get_status_summary()
        promotion = self.promotion.get(pipeline.state.run_id)
        if promotion is None:
            promotion = {"state": "pending" if summary["execution_status"] == "COMPLETED" else "not_applicable"}
        summary["promotion"] = promotion
        return summary

    def _persist(self, pipeline: ForgePipeline) -> None:
        self.store.save_run_summary(pipeline.state.project_id, pipeline.state.run_id, self._summary(pipeline))

    def start_run(self, project_id: str, prompt: str, simulate_failure: Optional[str] = None) -> Dict[str, Any]:
        project = self.store.load_project(project_id)
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        previous = None
        if project.get("current_run_id"):
            previous = self.store.read_spec(project_id, project["current_run_id"], "requirements.json")
        run_path = self.store.register_run(project_id, run_id, prompt, {"simulate_failure": simulate_failure,
                                                                        "iteration_of": project.get("current_run_id")})
        pipeline = ForgePipeline(
            user_prompt=prompt, project_id=project_id, run_id=run_id, output_dir=str(run_path),
            artifact_manager=self.artifact_manager, pipeline_logger=self.pipeline_logger,
            simulate_failure=simulate_failure, previous_requirements=previous, on_update=self._persist,
        )
        with self._lock:
            self.active[run_id] = pipeline
        self._persist(pipeline)
        self._executor.submit(self._execute, pipeline)
        return {"project_id": project_id, "run_id": run_id, "status": "PENDING"}

    def refinement_base(self, project_id: str) -> Dict[str, Any]:
        """The live version a refinement starts from (verified), or RefinementUnavailable."""
        project = self.store.load_project(project_id)
        base_run, base_version = project.get("current_run_id"), project.get("current_version")
        if not base_run or not base_version:
            raise RefinementUnavailable("This project has no live version to refine yet. Wait for a build to finish "
                                        "successfully, or start a new build from a description.")
        base_dir = self.store.run_dir(project_id, base_run)
        problems = verify_manifest(base_dir / "app")
        if problems:
            raise RefinementUnavailable("The live version's files failed their integrity check ("
                                        + "; ".join(problems[:3]) + "); roll back or rebuild before refining.")
        previous = self.store.read_spec(project_id, base_run, "requirements.json")
        if not previous:
            raise RefinementUnavailable("The live version has no stored requirements to refine.")
        return {"base_run_id": base_run, "base_version": base_version, "base_dir": base_dir, "previous": previous}

    def start_refinement(self, project_id: str, change_request: str, simulate_failure: Optional[str] = None,
                         approved: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Refine the live version: the run starts from its files and only the agents the change needs rewrite theirs.

        ``approved``: the refined specification the user approved in the plan preview; it is applied as is.
        """
        base = self.refinement_base(project_id)
        if self.has_active_run(project_id):
            raise ProjectBusy("A build is already running for this project. Wait for it to finish, then refine the app.")
        base_run, base_version, base_dir, previous = base["base_run_id"], base["base_version"], base["base_dir"], base["previous"]
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        run_path = self.store.register_run(project_id, run_id, change_request, {
            "simulate_failure": simulate_failure, "iteration_of": base_run, "mode": "refine", "base_version": base_version,
            "approved_in_preview": approved is not None})
        pipeline = ForgePipeline(
            user_prompt=change_request, project_id=project_id, run_id=run_id, output_dir=str(run_path),
            artifact_manager=self.artifact_manager, pipeline_logger=self.pipeline_logger,
            simulate_failure=simulate_failure, previous_requirements=previous, on_update=self._persist,
            refine={"base_run_id": base_run, "base_version": base_version, "base_dir": str(base_dir),
                    "change_request": change_request, "approved": approved},
        )
        with self._lock:
            self.active[run_id] = pipeline
        self._persist(pipeline)
        self._executor.submit(self._execute, pipeline)
        return {"project_id": project_id, "run_id": run_id, "status": "PENDING", "mode": "refine",
                "base_version": base_version}

    def _execute(self, pipeline: ForgePipeline) -> None:
        pid, rid = pipeline.state.project_id, pipeline.state.run_id
        try:
            pipeline.run_pipeline()
            if pipeline.state.execution_status == AgentStatus.COMPLETED:
                try:
                    entry = self.store.promote(pid, rid, source="run")
                except Exception as exc:  # integrity/lock problems: report, keep previous version
                    self.promotion[rid] = {"state": "failed", "error": str(exc)[:500]}
                    self.pipeline_logger.log_agent_message(rid, pid, "orchestrator", f"Promotion failed: {exc}", "error")
                else:
                    self.pipeline_logger.log_version_promoted(rid, pid, f"Run {rid} promoted to stable version {entry['version']}")
                    if self.on_promoted:
                        self.on_promoted(pid)
                    self.promotion[rid] = {"state": "promoted", "version": entry["version"]}
            else:
                self.promotion[rid] = {"state": "not_applicable"}
                self.pipeline_logger.log_agent_message(
                    rid, pid, "orchestrator",
                    "Run failed; the previous stable version (if any) remains active", "warning")
        except Exception as exc:  # unexpected orchestrator error: never leave the run "RUNNING"
            logger.exception("Run %s crashed", rid)
            pipeline.state.execution_status = AgentStatus.FAILED
            pipeline.state.error_reports["orchestrator"] = str(exc)
        finally:
            self._persist(pipeline)
            with self._lock:
                self.active.pop(rid, None)

    def get_summary(self, project_id: str, run_id: str) -> Dict[str, Any]:
        with self._lock:
            pipeline = self.active.get(run_id)
        if pipeline is not None and pipeline.state.project_id == project_id:
            return self._summary(pipeline)
        run = self.store.load_run(project_id, run_id)
        summary = run.get("summary") or {}
        summary.setdefault("project_id", project_id)
        summary.setdefault("run_id", run_id)
        summary.setdefault("execution_status", run.get("execution_status", "UNKNOWN"))
        summary["user_prompt"] = run.get("user_prompt", summary.get("user_prompt"))
        return summary

    def has_active_run(self, project_id: str) -> bool:
        with self._lock:
            return any(p.state.project_id == project_id for p in self.active.values())

    def forget_project(self, run_ids) -> None:
        for run_id in run_ids:
            self.promotion.pop(run_id, None)

    def is_active(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self.active

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
