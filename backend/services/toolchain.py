"""Shared frontend build toolchain for generated React apps.

Generated projects live under ``<workspace>/projects/...``. Installing React/Vite once into
``<workspace>/node_modules`` lets Node's upward module resolution serve every generated frontend,
so QA can run a real ``vite build`` in seconds instead of a full ``npm install`` per project.
Each generated project still ships its own package.json for standalone use.
"""

import json
import logging
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional, Tuple

from backend.codegen.frontend_writer import FRONTEND_DEPENDENCIES, FRONTEND_DEV_DEPENDENCIES
from backend.config import workspace_dir

logger = logging.getLogger("forge.toolchain")
_lock = threading.Lock()

REQUIRED_MODULES = ["react", "react-dom", "react-router-dom", "vite", "@vitejs/plugin-react"]


def node_available() -> bool:
    return shutil.which("node") is not None and shutil.which("npm") is not None


def toolchain_root() -> Path:
    return workspace_dir()


def is_ready() -> bool:
    modules = toolchain_root() / "node_modules"
    return all((modules / name / "package.json").is_file() for name in REQUIRED_MODULES) and (
        modules / "vite" / "bin" / "vite.js"
    ).is_file()


def ensure_toolchain(log: Optional[Callable[[str], None]] = None, timeout: int = 900) -> Tuple[bool, str]:
    """Install the shared toolchain if needed. Returns (ready, message)."""
    log = log or logger.info
    if is_ready():
        return True, "Frontend toolchain ready"
    if not node_available():
        return False, "Node.js/npm not found on PATH; frontend build cannot run"
    with _lock:
        if is_ready():
            return True, "Frontend toolchain ready"
        root = toolchain_root()
        package = {
            "name": "forge-ai-generated-apps-toolchain",
            "private": True,
            "description": "Shared React/Vite toolchain used by FORGE AI to build generated frontends",
            "dependencies": {**FRONTEND_DEPENDENCIES, **FRONTEND_DEV_DEPENDENCIES},
        }
        (root / "package.json").write_text(json.dumps(package, indent=2), encoding="utf-8")
        log("Installing shared frontend toolchain (react, react-router-dom, vite) - first run only")
        npm = shutil.which("npm")
        try:
            proc = subprocess.run(
                [npm, "install", "--no-audit", "--no-fund", "--loglevel=error"],
                cwd=str(root), capture_output=True, text=True, timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            return False, f"npm install timed out after {timeout}s"
        if proc.returncode != 0:
            return False, f"npm install failed: {(proc.stderr or proc.stdout)[-1500:]}"
    return (is_ready(), "Frontend toolchain installed" if is_ready() else "Toolchain install incomplete")


def build_frontend(frontend_dir: Path, timeout: int = 300) -> Tuple[bool, str]:
    """Run ``vite build`` for a generated frontend using the shared toolchain."""
    vite = toolchain_root() / "node_modules" / "vite" / "bin" / "vite.js"
    node = shutil.which("node")
    if not node or not vite.is_file():
        return False, "Frontend toolchain is not installed"
    frontend_dir = Path(frontend_dir).resolve()
    if toolchain_root().resolve() not in frontend_dir.parents:
        return False, "Generated frontend must live inside the FORGE workspace to use the shared toolchain"
    try:
        proc = subprocess.run(
            [node, str(vite), "build", "--logLevel", "warn"],
            cwd=str(frontend_dir), capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return False, f"vite build timed out after {timeout}s"
    output = (proc.stdout + "\n" + proc.stderr).strip()
    ok = proc.returncode == 0 and (frontend_dir / "dist" / "index.html").is_file()
    return ok, output[-4000:]
