"""Authentication Agent code writer: password hashing, JWT, RBAC, auth/user routers and frontend auth."""

import json
from typing import Dict, List

from backend.codegen.blueprint import Blueprint
from backend.codegen.project_files import GeneratedProject

AGENT = "auth"
TOKEN_MINUTES = 60
HASH_ITERATIONS = 200_000


def role_permissions(bp: Blueprint, api_spec: Dict) -> Dict[str, List[str]]:
    """Build the role -> permission matrix from the Backend agent's endpoint contract."""
    matrix: Dict[str, set] = {role: set() for role in bp.roles}
    for ep in api_spec.get("endpoints", []):
        perm = ep.get("required_permission")
        if not perm:
            continue
        for role in ep.get("required_roles") or []:
            if role in matrix:
                matrix[role].add(perm)
    for role in bp.roles:
        matrix[role].add("profile:read")
        if role in bp.admin_roles:
            matrix[role] = {"*"}
    return {role: sorted(perms) for role, perms in matrix.items()}


def build_auth_spec(bp: Blueprint, api_spec: Dict) -> Dict:
    perms = role_permissions(bp, api_spec)
    protected = [
        {"path": ep["path"], "method": ep["method"], "required_roles": ep.get("required_roles", []),
         "required_permissions": [ep["required_permission"]] if ep.get("required_permission") else [],
         "row_level_scope": ep.get("row_level_scope")}
        for ep in api_spec.get("endpoints", []) if ep.get("requires_auth")
    ]
    protected += [
        {"path": "/api/users", "method": "GET", "required_roles": bp.admin_roles, "required_permissions": ["users:manage"], "row_level_scope": None},
        {"path": "/api/users/{item_id}", "method": "PUT", "required_roles": bp.admin_roles, "required_permissions": ["users:manage"], "row_level_scope": None},
        {"path": "/api/users/{item_id}", "method": "DELETE", "required_roles": bp.admin_roles, "required_permissions": ["users:manage"], "row_level_scope": None},
    ]
    return {
        "project_name": bp.project_name,
        "password_security": {
            "hashing_algorithm": "pbkdf2_sha256",
            "bcrypt_rounds": 0,
            "min_length": 8,
            "require_uppercase": False,
            "require_lowercase": False,
            "require_digit": True,
            "require_special_char": False,
        },
        "jwt_strategy": {
            "algorithm": "HS256",
            "access_token_expire_minutes": TOKEN_MINUTES,
            "refresh_token_expire_days": 0,
            "secret_key_env_var": "SECRET_KEY",
            "token_type": "Bearer",
            "claims": ["sub", "email", "role", "iat", "exp"],
        },
        "auth_endpoints": [
            {"name": "register", "path": "/api/auth/register", "method": "POST", "requires_authentication": False,
             "description": f"Create an account with the '{bp.default_role}' role and return an access token.",
             "request_fields": ["email", "full_name", "password"], "response_fields": ["access_token", "token_type", "expires_in", "user"]},
            {"name": "login", "path": "/api/auth/login", "method": "POST", "requires_authentication": False,
             "description": "Verify credentials (PBKDF2) and issue a signed HS256 JWT.",
             "request_fields": ["email", "password"], "response_fields": ["access_token", "token_type", "expires_in", "user"]},
            {"name": "me", "path": "/api/auth/me", "method": "GET", "requires_authentication": True,
             "description": "Return the authenticated user's profile.", "request_fields": [],
             "response_fields": ["id", "email", "full_name", "role", "is_active"]},
            {"name": "list_users", "path": "/api/users", "method": "GET", "requires_authentication": True,
             "description": "Admin: list and search users.", "request_fields": [], "response_fields": ["items", "total"]},
            {"name": "update_user", "path": "/api/users/{item_id}", "method": "PUT", "requires_authentication": True,
             "description": "Admin: change a user's role, name or active flag.", "request_fields": ["full_name", "role", "is_active"],
             "response_fields": ["id", "role", "is_active"]},
            {"name": "delete_user", "path": "/api/users/{item_id}", "method": "DELETE", "requires_authentication": True,
             "description": "Admin: delete a user (and their owned records).", "request_fields": [], "response_fields": ["message"]},
        ],
        "rbac_roles": [
            {"role_name": role, "description": ("Administrator" if role in bp.admin_roles else f"{role.capitalize()} account"),
             "permissions": perms[role]}
            for role in bp.roles
        ],
        "user_entity_requirements": {"required_fields": [
            {"name": f.name, "type": f.pg_type, "description": f.label} for f in bp.user.fields
        ]},
        "protected_endpoints": protected,
        "security_middlewares": [
            {"name": "CORSMiddleware", "description": "Restrict browser origins (CORS_ORIGINS env)", "configuration": {"allow_origins_env": "CORS_ORIGINS"}},
        ],
        "password_reset_workflow": {},
        "email_verification_workflow": {},
    }


def render_security(bp: Blueprint, perms: Dict[str, List[str]]) -> str:
    perm_lines = "\n".join(
        f"    {json.dumps(role)}: " + ("{" + ", ".join(repr(x) for x in p) + "}" if p else "set()") + ","
        for role, p in perms.items()
    )
    return f'''"""Authentication and authorization (generated by FORGE AI Authentication Agent from auth_spec.json).

* Passwords: PBKDF2-HMAC-SHA256 with a per-user random salt.
* Sessions: stateless HS256 JSON Web Tokens signed with SECRET_KEY.
* Authorization: role -> permission matrix (ROLE_PERMISSIONS) + row-level ownership checks in routers.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

logger = logging.getLogger("auth")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "{TOKEN_MINUTES}"))
PASSWORD_HASH_ITERATIONS = int(os.getenv("PASSWORD_HASH_ITERATIONS", "{HASH_ITERATIONS}"))
MIN_PASSWORD_LENGTH = 8

_SECRET = os.getenv("SECRET_KEY")
if not _SECRET:
    _SECRET = secrets.token_urlsafe(48)
    logger.warning("SECRET_KEY is not set; using an ephemeral key (tokens become invalid on restart).")
_SECRET_BYTES = _SECRET.encode("utf-8")

ROLES = {json.dumps(bp.roles)}
ADMIN_ROLES = set({json.dumps(bp.admin_roles)})
DEFAULT_ROLE = {json.dumps(bp.default_role)}
ROLE_PERMISSIONS = {{
{perm_lines}
}}


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS)
    return f"pbkdf2_sha256${{PASSWORD_HASH_ITERATIONS}}${{_b64encode(salt)}}${{_b64encode(digest)}}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _b64decode(salt), int(iterations))
        return hmac.compare_digest(candidate, _b64decode(digest))
    except (ValueError, TypeError):
        return False


def password_problem(password: str) -> Optional[str]:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {{MIN_PASSWORD_LENGTH}} characters long"
    if not any(c.isdigit() for c in password) or not any(c.isalpha() for c in password):
        return "Password must contain at least one letter and one digit"
    return None


def create_access_token(user: User) -> str:
    now = int(time.time())
    header = {{"alg": ALGORITHM, "typ": "JWT"}}
    payload = {{"sub": str(user.id), "email": user.email, "role": user.role, "iat": now,
               "exp": now + ACCESS_TOKEN_EXPIRE_MINUTES * 60}}
    signing_input = f"{{_b64encode(json.dumps(header, separators=(',', ':')).encode())}}.{{_b64encode(json.dumps(payload, separators=(',', ':')).encode())}}"
    signature = hmac.new(_SECRET_BYTES, signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{{signing_input}}.{{_b64encode(signature)}}"


def decode_access_token(token: str) -> dict:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        expected = hmac.new(_SECRET_BYTES, f"{{header_b64}}.{{payload_b64}}".encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(signature_b64)):
            raise ValueError("bad signature")
        header = json.loads(_b64decode(header_b64))
        if header.get("alg") != ALGORITHM:
            raise ValueError("unexpected algorithm")
        payload = json.loads(_b64decode(payload_b64))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token",
                            headers={{"WWW-Authenticate": "Bearer"}}) from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired",
                            headers={{"WWW-Authenticate": "Bearer"}})
    return payload


_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated",
                            headers={{"WWW-Authenticate": "Bearer"}})
    payload = decode_access_token(credentials.credentials)
    try:
        user = db.get(User, int(payload.get("sub")))
    except (TypeError, ValueError):
        user = None
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive",
                            headers={{"WWW-Authenticate": "Bearer"}})
    return user


def is_admin(user: User) -> bool:
    return user.role in ADMIN_ROLES


def has_permission(user: User, permission: str) -> bool:
    granted = ROLE_PERMISSIONS.get(user.role, set())
    return "*" in granted or permission in granted


def require_permission(permission: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Role '{{user.role}}' lacks permission '{{permission}}'")
        return user

    return dependency


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return dependency
'''


def render_auth_schemas(bp: Blueprint) -> str:
    roles = ", ".join(repr(r) for r in bp.roles)
    return f'''"""Schemas for authentication and user management (generated by FORGE AI Authentication Agent)."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

EMAIL_PATTERN = r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$"
RoleName = Literal[{roles}]


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=255, pattern=EMAIL_PATTERN)
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UserAdminUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    role: Optional[RoleName] = None
    is_active: Optional[bool] = None


class UserPage(BaseModel):
    items: List[UserOut]
    total: int
    skip: int
    limit: int
'''


def render_auth_router(bp: Blueprint) -> str:
    return '''"""Registration, login and profile endpoints (generated by FORGE AI Authentication Agent)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth_schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.database import get_db
from app.models import User
from app.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    DEFAULT_ROLE,
    create_access_token,
    get_current_user,
    hash_password,
    password_problem,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user),
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    problem = password_problem(payload.password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(email=email, full_name=payload.full_name.strip(), role=DEFAULT_ROLE, is_active=True,
                hashed_password=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
'''


def render_users_router(bp: Blueprint) -> str:
    return '''"""Administrator user management (generated by FORGE AI Authentication Agent)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth_schemas import UserAdminUpdate, UserOut, UserPage
from app.database import get_db
from app.models import User
from app.schemas import MessageResponse
from app.security import is_admin, require_permission

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.get("", response_model=UserPage)
def list_users(
    q: Optional[str] = None,
    role: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_permission("users:manage")),
):
    stmt = select(User)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))
    if role:
        stmt = stmt.where(User.role == role)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.order_by(User.id).offset(skip).limit(limit)).all()
    return UserPage(items=items, total=total, skip=skip, limit=limit)


@router.put("/{item_id}", response_model=UserOut)
def update_user(item_id: int, payload: UserAdminUpdate, db: Session = Depends(get_db),
                admin: User = Depends(require_permission("users:manage"))):
    user = db.get(User, item_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    changes = payload.model_dump(exclude_unset=True)
    if user.id == admin.id and (changes.get("is_active") is False or
                                ("role" in changes and changes["role"] != admin.role)):
        raise HTTPException(status_code=400, detail="You cannot disable or demote your own account")
    for field, value in changes.items():
        if value is not None:
            setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{item_id}", response_model=MessageResponse)
def delete_user(item_id: int, db: Session = Depends(get_db), admin: User = Depends(require_permission("users:manage"))):
    user = db.get(User, item_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    db.delete(user)
    db.commit()
    return MessageResponse(message=f"User {item_id} deleted")
'''


def render_seed(bp: Blueprint) -> str:
    admin_role = bp.admin_roles[0]
    return f'''"""Initial data (generated by FORGE AI Authentication Agent).

Creates the first administrator from ADMIN_EMAIL / ADMIN_PASSWORD when both are set and the account
does not exist yet. Credentials are never hard-coded in the generated source.
"""

import os

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import User
from app.security import hash_password


def seed_admin() -> None:
    email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD") or ""
    if not email or not password:
        return
    with SessionLocal() as db:
        if db.scalar(select(User).where(func.lower(User.email) == email)):
            return
        db.add(User(email=email, full_name=os.getenv("ADMIN_NAME", "Administrator"), role="{admin_role}",
                    is_active=True, hashed_password=hash_password(password)))
        db.commit()
'''


# ---------------------------------------------------------------------------------------------
# Frontend auth (React)
# ---------------------------------------------------------------------------------------------

AUTH_CONTEXT_JSX = """import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api, setAuthToken, getAuthToken } from '../api/client.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getAuthToken()));

  useEffect(() => {
    if (!getAuthToken()) return;
    api.get('/api/auth/me')
      .then(setUser)
      .catch(() => setAuthToken(null))
      .finally(() => setLoading(false));
  }, []);

  const handleToken = useCallback((data) => {
    setAuthToken(data.access_token);
    setUser(data.user);
    return data.user;
  }, []);

  const login = useCallback((email, password) => api.post('/api/auth/login', { email, password }).then(handleToken), [handleToken]);
  const register = useCallback((payload) => api.post('/api/auth/register', payload).then(handleToken), [handleToken]);
  const logout = useCallback(() => { setAuthToken(null); setUser(null); }, []);

  const value = useMemo(() => ({
    user, loading, login, register, logout,
    isAdmin: Boolean(user && __ADMIN_ROLES__.includes(user.role)),
  }), [user, loading, login, register, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
"""

PROTECTED_ROUTE_JSX = """import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from './AuthContext.jsx';

export default function ProtectedRoute({ children, adminOnly = false }) {
  const { user, loading, isAdmin } = useAuth();
  const location = useLocation();
  if (loading) return <div className="page-loading">Loading…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (adminOnly && !isAdmin) return <div className="card empty-state"><h2>Access denied</h2><p>This page is only available to administrators.</p></div>;
  return children;
}
"""

LOGIN_PAGE_JSX = """import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext.jsx';
import { APP_NAME } from '../config/app.js';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ email: '', password: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setBusy(true);
    try {
      await login(form.email, form.password);
      navigate(location.state?.from || '/', { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>{APP_NAME}</h1>
        <p className="muted">Sign in to continue</p>
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        <label>Email<input type="email" required autoComplete="email" value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
        <label>Password<input type="password" required autoComplete="current-password" value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
        <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        <p className="muted">No account? <Link to="/register">Create one</Link></p>
      </form>
    </div>
  );
}
"""

REGISTER_PAGE_JSX = """import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext.jsx';
import { APP_NAME } from '../config/app.js';

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: '', email: '', password: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    if (form.password.length < 8 || !/[0-9]/.test(form.password) || !/[A-Za-z]/.test(form.password)) {
      setError('Password must be at least 8 characters and contain a letter and a digit.');
      return;
    }
    setBusy(true);
    try {
      await register(form);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>{APP_NAME}</h1>
        <p className="muted">Create your account</p>
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        <label>Full name<input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
        <label>Email<input type="email" required autoComplete="email" value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
        <label>Password<input type="password" required autoComplete="new-password" value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
        <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Creating account…' : 'Create account'}</button>
        <p className="muted">Already registered? <Link to="/login">Sign in</Link></p>
      </form>
    </div>
  );
}
"""


def write_auth_files(bp: Blueprint, project: GeneratedProject, api_spec: Dict) -> List[str]:
    perms = role_permissions(bp, api_spec)
    project.write("backend/app/security.py", render_security(bp, perms), AGENT)
    project.write("backend/app/auth_schemas.py", render_auth_schemas(bp), AGENT)
    project.write("backend/app/routers/auth.py", render_auth_router(bp), AGENT)
    project.write("backend/app/routers/users.py", render_users_router(bp), AGENT)
    project.write("backend/app/seed.py", render_seed(bp), AGENT)
    project.write("frontend/src/auth/AuthContext.jsx",
                  AUTH_CONTEXT_JSX.replace("__ADMIN_ROLES__", json.dumps(bp.admin_roles)), AGENT)
    project.write("frontend/src/auth/ProtectedRoute.jsx", PROTECTED_ROUTE_JSX, AGENT)
    project.write("frontend/src/pages/LoginPage.jsx", LOGIN_PAGE_JSX, AGENT)
    project.write("frontend/src/pages/RegisterPage.jsx", REGISTER_PAGE_JSX, AGENT)
    return project.files_by_agent(AGENT)
