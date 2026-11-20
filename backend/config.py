"""Central configuration for the FORGE AI platform.

Environment variables are loaded from ``backend/.env`` (preferred) or a repo-level ``.env``.
Nothing secret is ever written by the platform into tracked files.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

load_dotenv(BACKEND_DIR / ".env")
load_dotenv(REPO_ROOT / ".env")


def workspace_dir() -> Path:
    """Root directory for generated projects, artifacts, logs and the shared frontend toolchain."""
    path = Path(os.getenv("FORGE_WORKSPACE", str(REPO_ROOT / "workspace"))).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
