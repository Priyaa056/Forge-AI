"""Persistent project / run registry, stable-version promotion and file-level rollback.

Layout (inside the git-ignored workspace)::

    workspace/projects/<project_id>/project.json      project metadata, runs, version history
    workspace/projects/<project_id>/runs/<run_id>/    run.json, specs/*.json, app/ (immutable snapshot)
    workspace/projects/<project_id>/current/          materialised active (stable) version of the app

A run whose seven agents all succeed (QA passed, deploy health check passed) is *promoted*: its
snapshot is verified against its checksum manifest and copied atomically into ``current/``.
A failed run never touches ``current/`` - the last stable version stays live (recovery).
Rollback re-materialises an earlier stable snapshot into ``current/`` **and** restores all seven
stage artifacts from that run as new artifact versions, so files and artifacts stay consistent.
"""

import json
import os
import re
import secrets
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.artifacts.artifact_manager import ArtifactManager
from backend.artifacts.artifact_schema import ArtifactStatus
from backend.codegen.project_files import IGNORED_DIRS, verify_manifest
from backend.config import workspace_dir
from backend.monitoring.logger import PipelineLogger

ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
STAGES = ["pm", "ui", "backend", "db", "auth", "qa", "deploy"]


class ProjectNotFound(KeyError):
    pass


class RollbackRejected(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def valid_id(value: str) -> bool:
    return bool(value and ID_RE.match(value))


class ProjectStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root or (workspace_dir() / "projects"))
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, threading.Lock] = {}
        self._global = threading.Lock()

    # ------------------------------------------------------------------ paths
    def _lock(self, project_id: str) -> threading.Lock:
        with self._global:
            return self._locks.setdefault(project_id, threading.Lock())

    def project_dir(self, project_id: str) -> Path:
        if not valid_id(project_id):
            raise ProjectNotFound(project_id)
        return self.root / project_id

    def run_dir(self, project_id: str, run_id: str) -> Path:
        if not valid_id(run_id):
            raise ProjectNotFound(run_id)
        return self.project_dir(project_id) / "runs" / run_id

    def current_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "current"

    # ------------------------------------------------------------------ projects
    def create_project(self, prompt: str, name: Optional[str] = None, owner_id: Optional[str] = None) -> Dict[str, Any]:
        project_id = f"proj_{uuid.uuid4().hex[:10]}"
        path = self.project_dir(project_id)
        path.mkdir(parents=True)
        data = {
            "project_id": project_id,
            "owner_id": owner_id,
            "name": name or (prompt.strip()[:60] + ("…" if len(prompt.strip()) > 60 else "")),
            "initial_prompt": prompt,
            "created_at": _now(),
            "updated_at": _now(),
            "runs": [],
            "versions": [],
            "current_version": None,
            "current_run_id": None,
            # Local-only credentials for the generated app's preview admin (workspace is git-ignored).
            "preview_admin": {"email": "admin@example.com", "password": "Preview-" + secrets.token_urlsafe(8) + "9"},
        }
        _write_json(path / "project.json", data)
        return data

    def load_project(self, project_id: str) -> Dict[str, Any]:
        path = self.project_dir(project_id) / "project.json"
        if not path.is_file():
            raise ProjectNotFound(project_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def save_project(self, data: Dict[str, Any]) -> None:
        data["updated_at"] = _now()
        _write_json(self.project_dir(data["project_id"]) / "project.json", data)

    def list_projects(self, owner_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List projects; with ``owner_id`` only that user's projects are returned."""
        items = []
        for path in self.root.glob("*/project.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if owner_id is not None and data.get("owner_id") != owner_id:
                continue
            last_run = self.load_run(data["project_id"], data["runs"][-1]) if data.get("runs") else None
            items.append({
                "project_id": data["project_id"], "name": data.get("project_name") or data["name"],
                "initial_prompt": data.get("initial_prompt"),
                "created_at": data["created_at"], "updated_at": data["updated_at"],
                "run_count": len(data.get("runs", [])), "current_version": data.get("current_version"),
                "current_run_id": data.get("current_run_id"),
                "last_status": (last_run or {}).get("execution_status"),
            })
        return sorted(items, key=lambda x: x["updated_at"], reverse=True)

    def adopt_unowned_projects(self, owner_id: str) -> int:
        """Assign projects created before platform accounts existed to ``owner_id`` (first account only)."""
        adopted = 0
        for path in self.root.glob("*/project.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if data.get("owner_id"):
                continue
            with self._lock(data["project_id"]):
                data["owner_id"] = owner_id
                _write_json(path, data)
            adopted += 1
        return adopted

    # ------------------------------------------------------------------ runs
    def register_run(self, project_id: str, run_id: str, prompt: str, options: Dict[str, Any]) -> Path:
        with self._lock(project_id):
            data = self.load_project(project_id)
            run_path = self.run_dir(project_id, run_id)
            run_path.mkdir(parents=True, exist_ok=False)
            data["runs"].append(run_id)
            self.save_project(data)
        _write_json(run_path / "run.json", {
            "project_id": project_id, "run_id": run_id, "user_prompt": prompt, "created_at": _now(),
            "execution_status": "PENDING", "options": options, "summary": None,
        })
        return run_path

    def save_run_summary(self, project_id: str, run_id: str, summary: Dict[str, Any]) -> None:
        path = self.run_dir(project_id, run_id) / "run.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {"project_id": project_id, "run_id": run_id}
        data["execution_status"] = summary.get("execution_status")
        data["summary"] = summary
        data["updated_at"] = _now()
        _write_json(path, data)
        if summary.get("agents", {}).get("pm", {}).get("status") == "COMPLETED":
            with self._lock(project_id):
                project = self.load_project(project_id)
                if not project.get("project_name"):
                    spec = self.read_spec(project_id, run_id, "requirements.json")
                    if spec:
                        project["project_name"] = spec.get("project_name")
                        self.save_project(project)

    def load_run(self, project_id: str, run_id: str) -> Dict[str, Any]:
        path = self.run_dir(project_id, run_id) / "run.json"
        if not path.is_file():
            raise ProjectNotFound(run_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def read_spec(self, project_id: str, run_id: str, filename: str) -> Optional[Dict[str, Any]]:
        path = self.run_dir(project_id, run_id) / "specs" / filename
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def app_dir(self, project_id: str, run_id: Optional[str] = None) -> Path:
        return self.run_dir(project_id, run_id) / "app" if run_id else self.current_dir(project_id)

    # ------------------------------------------------------------------ versions
    def _materialise(self, project_id: str, source_app: Path) -> None:
        problems = verify_manifest(source_app)
        if problems:
            raise RollbackRejected("Snapshot integrity check failed: " + "; ".join(problems[:5]))
        project_path = self.project_dir(project_id)
        staging = project_path / f"current.staging-{uuid.uuid4().hex[:6]}"
        shutil.copytree(source_app, staging, ignore=shutil.ignore_patterns("node_modules", "__pycache__",
                                                                          ".pytest_cache", ".forge_runtime"))
        problems = verify_manifest(staging)
        if problems:
            shutil.rmtree(staging, ignore_errors=True)
            raise RollbackRejected("Copied snapshot failed verification: " + "; ".join(problems[:5]))
        current = self.current_dir(project_id)
        retired = project_path / f"current.retired-{uuid.uuid4().hex[:6]}"
        if current.exists():
            for attempt in range(5):
                try:
                    os.replace(current, retired)
                    break
                except PermissionError:  # Windows: a file may be briefly locked (e.g. a preview server)
                    time.sleep(0.5)
            else:
                shutil.rmtree(staging, ignore_errors=True)
                raise RollbackRejected("The current version is locked (stop the preview and try again)")
        os.replace(staging, current)
        shutil.rmtree(retired, ignore_errors=True)

    def promote(self, project_id: str, run_id: str, source: str = "run", reason: Optional[str] = None,
                restored_from_version: Optional[int] = None) -> Dict[str, Any]:
        """Make a run's snapshot the active version (verified copy into current/)."""
        with self._lock(project_id):
            project = self.load_project(project_id)
            self._materialise(project_id, self.app_dir(project_id, run_id))
            version = (project["versions"][-1]["version"] + 1) if project["versions"] else 1
            entry = {"version": version, "run_id": run_id, "source": source, "promoted_at": _now(),
                     "reason": reason, "restored_from_version": restored_from_version}
            project["versions"].append(entry)
            project["current_version"] = version
            project["current_run_id"] = run_id
            self.save_project(project)
            return entry

    def stable_runs(self, project_id: str) -> List[str]:
        project = self.load_project(project_id)
        return list(dict.fromkeys(v["run_id"] for v in project["versions"] if v["source"] == "run"))

    def rollback(self, project_id: str, target_run_id: str, artifact_manager: ArtifactManager,
                 pipeline_logger: PipelineLogger, reason: Optional[str] = None) -> Dict[str, Any]:
        """Restore a previous stable version: artifacts (all 7 stages) + generated files, atomically."""
        project = self.load_project(project_id)
        if target_run_id not in self.stable_runs(project_id):
            raise RollbackRejected(f"Run '{target_run_id}' never produced a stable (fully validated) version")
        if project.get("current_run_id") == target_run_id:
            raise RollbackRejected("That version is already the active version")
        target_version = next(v["version"] for v in project["versions"] if v["run_id"] == target_run_id and v["source"] == "run")
        rollback_run_id = f"rb_{uuid.uuid4().hex[:8]}"
        pipeline_logger.log_rollback_started(run_id=rollback_run_id, project_id=project_id, agent_name="project",
                                             target_version=target_version,
                                             message=f"Project rollback to version {target_version} (run {target_run_id}) requested")
        started = time.monotonic()
        try:
            run_artifacts = {a.agent_name: a for a in artifact_manager.list_artifacts(project_id=project_id, run_id=target_run_id)
                             if a.status == ArtifactStatus.COMPLETED}
            missing = [s for s in STAGES if s not in run_artifacts]
            if missing:
                raise RollbackRejected(f"Target run lacks completed artifacts for: {', '.join(missing)}")
            problems = verify_manifest(self.app_dir(project_id, target_run_id))
            if problems:
                raise RollbackRejected("Target snapshot integrity check failed: " + "; ".join(problems[:5]))

            restored: Dict[str, str] = {}
            previous_id = None
            for stage in STAGES:  # dependency order keeps lineage consistent
                source_art = run_artifacts[stage]
                current = artifact_manager.get_latest_artifact(project_id, stage)
                lineage = [x for x in (current.artifact_id if current else None, source_art.artifact_id, previous_id) if x]
                new_art = artifact_manager.create_artifact(
                    project_id=project_id, run_id=rollback_run_id, agent_name=stage, artifact_type=source_art.artifact_type,
                    content=source_art.content, input_artifacts=lineage, status=ArtifactStatus.COMPLETED,
                    metadata={"is_rollback": True, "restored_from_artifact_id": source_art.artifact_id,
                              "restored_from_version": source_art.version, "restored_from_run_id": target_run_id,
                              "reason": (reason or "")[:300]},
                )
                restored[stage] = new_art.artifact_id
                previous_id = new_art.artifact_id
            entry = self.promote(project_id, target_run_id, source="rollback", reason=reason,
                                 restored_from_version=target_version)
            duration = round((time.monotonic() - started) * 1000, 2)
            pipeline_logger.log_rollback_completed(run_id=rollback_run_id, project_id=project_id, agent_name="project",
                                                   target_version=target_version, restored_artifact_id=restored["deploy"],
                                                   duration_ms=duration)
            pipeline_logger.log_version_promoted(rollback_run_id, project_id,
                                                 f"Version {entry['version']} is now active (restored from version {target_version})")
            return {"status": "COMPLETED", "rollback_id": rollback_run_id, "project_id": project_id,
                    "target_run_id": target_run_id, "restored_from_version": target_version,
                    "new_version": entry["version"], "restored_artifacts": restored, "duration_ms": duration,
                    "files_verified": True}
        except Exception as exc:
            pipeline_logger.log_rollback_failed(run_id=rollback_run_id, project_id=project_id, agent_name="project",
                                                target_version=target_version, duration_ms=round((time.monotonic() - started) * 1000, 2),
                                                error_type=type(exc).__name__, error_message=str(exc))
            raise

    # ------------------------------------------------------------------ files
    def safe_file(self, base: Path, rel_path: str) -> Path:
        target = (base / rel_path).resolve()
        if base.resolve() not in target.parents or any(part in IGNORED_DIRS for part in Path(rel_path).parts):
            raise ProjectNotFound(rel_path)
        if not target.is_file():
            raise ProjectNotFound(rel_path)
        return target
