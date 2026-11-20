"""JSON-file user store for platform accounts (inside the git-ignored workspace)."""

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.auth.security import hash_password, verify_password
from backend.config import workspace_dir

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8


class UserExists(ValueError):
    pass


class InvalidUserInput(ValueError):
    pass


def public_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {k: user[k] for k in ("id", "email", "full_name", "created_at")}


class UserStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or (workspace_dir() / "users.json"))
        self._lock = threading.Lock()

    def _load(self) -> List[Dict[str, Any]]:
        if not self.path.is_file():
            return []
        return json.loads(self.path.read_text(encoding="utf-8")).get("users", [])

    def _save(self, users: List[Dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"users": users}, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    @staticmethod
    def normalize_email(email: str) -> str:
        return (email or "").strip().lower()

    def create(self, email: str, password: str, full_name: Optional[str] = None) -> Dict[str, Any]:
        email = self.normalize_email(email)
        if not EMAIL_RE.match(email) or len(email) > 255:
            raise InvalidUserInput("Enter a valid email address.")
        if len(password or "") < MIN_PASSWORD_LENGTH or len(password) > 128:
            raise InvalidUserInput(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        name = (full_name or "").strip()[:120] or email.split("@")[0]
        with self._lock:
            users = self._load()
            if any(u["email"] == email for u in users):
                raise UserExists("An account with this email already exists.")
            user = {
                "id": f"usr_{uuid.uuid4().hex[:12]}",
                "email": email,
                "full_name": name,
                "password_hash": hash_password(password),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            users.append(user)
            self._save(users)
        return user

    def authenticate(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        user = self.get_by_email(email)
        if user and verify_password(password or "", user["password_hash"]):
            return user
        return None

    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        email = self.normalize_email(email)
        return next((u for u in self._load() if u["email"] == email), None)

    def get(self, user_id: str) -> Optional[Dict[str, Any]]:
        return next((u for u in self._load() if u["id"] == user_id), None)

    def count(self) -> int:
        return len(self._load())
