"""Live preview of generated applications.

Starts the project's active version (``current/``) as a real uvicorn process that serves both the
generated REST API and the generated React build, on a free local port.
"""

import threading
from pathlib import Path
from typing import Any, Dict, Optional

from backend.services import toolchain
from backend.services.app_runner import GeneratedAppProcess
from backend.services.project_store import ProjectStore


class PreviewManager:
    def __init__(self, store: ProjectStore):
        self.store = store
        self.previews: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def status(self, project_id: str) -> Dict[str, Any]:
        project = self.store.load_project(project_id)
        with self._lock:
            entry = self.previews.get(project_id)
        running = bool(entry and entry["process"].is_running())
        return {
            "running": running,
            "url": entry["process"].url if running else None,
            "version": entry["version"] if entry else None,
            "current_version": project.get("current_version"),
            "stale": bool(running and entry["version"] != project.get("current_version")),
            "admin_email": project["preview_admin"]["email"],
            "admin_password": project["preview_admin"]["password"],
            "log_tail": entry["process"].read_log(3000) if entry else "",
            "message": entry.get("message") if entry else None,
        }

    def start(self, project_id: str) -> Dict[str, Any]:
        project = self.store.load_project(project_id)
        version = project.get("current_version")
        if not version:
            raise ValueError("This project has no stable version yet; preview becomes available after a successful run")
        self.stop(project_id)
        app_root = self.store.current_dir(project_id)
        message = None
        if not (app_root / "frontend" / "dist" / "index.html").is_file():
            # Normally QA has already built frontend/dist. Build here only if the shared toolchain exists;
            # never trigger a long npm install from a preview request.
            if toolchain.is_ready():
                ok, out = toolchain.build_frontend(app_root / "frontend")
                message = "Frontend built" if ok else f"Frontend build failed: {out[-300:]}"
            else:
                message = "Frontend bundle not available (toolchain not installed); the API is available at /docs."
        data_dir = self.store.project_dir(project_id) / "preview_data" / f"v{version}"
        proc = GeneratedAppProcess(app_root, data_dir=data_dir, admin_email=project["preview_admin"]["email"],
                                   admin_password=project["preview_admin"]["password"])
        ok = proc.start(timeout=60)
        with self._lock:
            self.previews[project_id] = {"process": proc, "version": version, "message": message}
        if not ok:
            log = proc.read_log(2000)
            proc.stop()
            raise RuntimeError(f"Generated application failed to start: {log[-800:]}")
        return self.status(project_id)

    def stop(self, project_id: str) -> None:
        with self._lock:
            entry = self.previews.pop(project_id, None)
        if entry:
            entry["process"].stop()

    def stop_all(self) -> None:
        for project_id in list(self.previews):
            self.stop(project_id)
