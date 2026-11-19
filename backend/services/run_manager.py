"""Background execution of pipeline runs with live, persisted progress."""

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from backend.artifacts.artifact_manager import ArtifactManager
from backend.artifacts.artifact_store import LocalJsonArtifactStore
from backend.config import env_int, workspace_dir
from backend.monitoring.logger import PipelineLogger
from backend.services.pipeline import AgentStatus, ForgePipeline
from backend.services.project_store import ProjectStore

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
