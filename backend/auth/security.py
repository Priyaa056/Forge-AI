"""Password hashing (PBKDF2-HMAC-SHA256) and HS256 bearer tokens for platform accounts.

The signing key comes from ``FORGE_SECRET_KEY``; when unset, a random key is generated once and
stored in the git-ignored workspace (``.forge_secret``) so sessions survive restarts.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict

from backend.config import env_int, workspace_dir

PBKDF2_ITERATIONS = env_int("FORGE_PASSWORD_ITERATIONS", 200_000)
TOKEN_TTL_SECONDS = env_int("FORGE_TOKEN_TTL_MINUTES", 12 * 60) * 60
_key_lock = threading.Lock()
_key_cache: Dict[str, bytes] = {}


class AuthError(Exception):
    """Invalid, expired or malformed credentials/token."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signing_key() -> bytes:
    configured = os.getenv("FORGE_SECRET_KEY", "").strip()
    if configured:
        return configured.encode("utf-8")
    path = workspace_dir() / ".forge_secret"
    cache_key = str(path)
    with _key_lock:
        if cache_key in _key_cache:
            return _key_cache[cache_key]
        if path.is_file():
            key = path.read_text(encoding="utf-8").strip().encode("utf-8")
        else:
            key = secrets.token_urlsafe(48).encode("utf-8")
            path.write_text(key.decode("utf-8"), encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        _key_cache[cache_key] = key
        return key


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _unb64(salt), int(iterations))
        return hmac.compare_digest(candidate, _unb64(digest))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, email: str) -> str:
    now = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub": user_id, "email": email, "iat": now, "exp": now + TOKEN_TTL_SECONDS},
                              separators=(",", ":")).encode())
    signature = hmac.new(_signing_key(), f"{header}.{payload}".encode("ascii"), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(signature)}"


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        header, payload, signature = token.split(".")
        expected = hmac.new(_signing_key(), f"{header}.{payload}".encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature)):
            raise AuthError("Invalid token")
        if json.loads(_unb64(header)).get("alg") != "HS256":
            raise AuthError("Invalid token")
        claims = json.loads(_unb64(payload))
    except (ValueError, TypeError) as exc:
        raise AuthError("Invalid token") from exc
    if int(claims.get("exp", 0)) < int(time.time()):
        raise AuthError("Session expired, please log in again")
    return claims


def token_ttl_seconds() -> int:
    return TOKEN_TTL_SECONDS


def secret_file() -> Path:
    return workspace_dir() / ".forge_secret"
