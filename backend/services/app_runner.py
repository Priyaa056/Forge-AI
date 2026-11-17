"""Start, probe and stop a generated application as a real process (used by Deploy health checks and Preview)."""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Tuple


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def http_request(url: str, method: str = "GET", body: Optional[Dict] = None, token: Optional[str] = None,
                 timeout: float = 10.0) -> Tuple[int, str, float]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), (time.monotonic() - start) * 1000
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace"), (time.monotonic() - start) * 1000
    except (urllib.error.URLError, OSError) as err:
        return 0, str(err), (time.monotonic() - start) * 1000


class GeneratedAppProcess:
    """A running uvicorn process for a generated app (backend + built frontend when available)."""

    def __init__(self, app_root: Path, port: Optional[int] = None, data_dir: Optional[Path] = None,
                 admin_email: str = "admin@example.com", admin_password: Optional[str] = None,
                 secret_key: Optional[str] = None):
        self.app_root = Path(app_root)
        self.backend_dir = self.app_root / "backend"
        self.port = port or free_port()
        self.data_dir = Path(data_dir or (self.app_root / ".forge_runtime"))
        self.admin_email = admin_email
        self.admin_password = admin_password or ("Adm1n-" + secrets.token_urlsafe(9))
        self.secret_key = secret_key or secrets.token_urlsafe(48)
        self.process: Optional[subprocess.Popen] = None
        self._log_handle = None
        self.log_path = self.data_dir / "server.log"

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def env(self) -> Dict[str, str]:
        env = dict(os.environ)
        for key in list(env):
            if key.startswith(("GOOGLE_", "GEMINI_", "FORGE_")) or key == "USE_LLM":
                env.pop(key)  # the generated app never needs platform secrets
        db_path = (self.data_dir / "app.db").as_posix()
        env.update({
            "DATABASE_URL": f"sqlite:///{db_path}",
            "SECRET_KEY": self.secret_key,
            "ADMIN_EMAIL": self.admin_email,
            "ADMIN_PASSWORD": self.admin_password,
            "CORS_ORIGINS": "*",
            "FRONTEND_DIST": str((self.app_root / "frontend" / "dist").resolve()),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        })
        return env

    def start(self, timeout: float = 45.0) -> bool:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        log = self._log_handle = open(self.log_path, "w", encoding="utf-8")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            # cwd is the runtime data dir (not the app tree) so the app directory can be swapped on Windows
            # during promotion/rollback while a preview is running.
            [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(self.backend_dir.resolve()),
             "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=str(self.data_dir), env=self.env(), stdout=log, stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                return False
            status, _body, _ms = http_request(f"{self.url}/health", timeout=2)
            if status == 200:
                return True
            time.sleep(0.4)
        return False

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def read_log(self, max_chars: int = 6000) -> str:
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace")[-max_chars:]
        except OSError:
            return ""

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None
