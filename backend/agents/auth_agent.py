"""Authentication Agent: registration, login, password hashing, JWT and role-based access control.

Inputs: requirements (PM), API contract (Backend) and database schema (DB).
Output: ``auth_spec.json`` (AuthOutput) + ``backend/app/security.py``, auth/user routers, seed and the
frontend auth context/pages. The RBAC matrix is derived from the permissions each endpoint declares.
"""

from typing import Any, Dict, List, Optional

from backend.agents.base_agent import BaseAgent
from backend.artifacts.artifact_context import ArtifactContext
from backend.codegen.auth_writer import build_auth_spec, write_auth_files
from backend.codegen.blueprint import build_blueprint
from backend.exceptions import GenerationError, ValidationError
from backend.schemas.auth_schema import AuthOutput
from backend.schemas.backend_schema import BackendOutput
from backend.schemas.db_schema import DBOutput
from backend.schemas.pm_schema import PMOutput

AGENT = "auth"
REQUIRED_USER_COLUMNS = {"id", "email", "hashed_password", "role", "is_active"}


class AuthAgent(BaseAgent[AuthOutput]):
    stage_name = AGENT

    def __init__(
        self,
        pm_output_path: str = "outputs/pm_output.json",
        backend_output_path: str = "outputs/backend_output.json",
        db_output_path: str = "outputs/db_output.json",
        output_filepath: str = "outputs/auth_output.json",
        artifact_context: Optional[ArtifactContext] = None,
        project: Optional[Any] = None,
        log_fn=None,
    ):
        super().__init__(output_schema_cls=AuthOutput, output_filepath=output_filepath,
                         artifact_context=artifact_context, project=project, log_fn=log_fn)
        self.pm_output_path = pm_output_path
        self.backend_output_path = backend_output_path
        self.db_output_path = db_output_path
        self.pm_data: Optional[PMOutput] = None
        self.backend_data: Optional[BackendOutput] = None
        self.db_data: Optional[DBOutput] = None
        self.api_spec: Dict[str, Any] = {}

    def load_inputs(self) -> None:
        self.pm_data = self.load_upstream("pm", PMOutput, self.pm_output_path)
        self.backend_data = self.load_upstream("backend", BackendOutput, self.backend_output_path)
        self.db_data = self.load_upstream("db", DBOutput, self.db_output_path, optional=True)

    def generate(self) -> Dict[str, Any]:
        if not self.pm_data or not self.backend_data:
            raise GenerationError("Inputs not loaded. Call load_inputs() first.")
        bp = build_blueprint(self.pm_data)
        if self.db_data is not None:
            users = next((t for t in self.db_data.tables if t.model_name == "User"), None)
            if users is None:
                raise ValidationError("Database schema has no User table; authentication cannot be implemented")
            missing = REQUIRED_USER_COLUMNS - {c.name for c in users.columns}
            if missing:
                raise ValidationError(f"User table lacks security columns: {', '.join(sorted(missing))}")
        self.api_spec = self.backend_data.model_dump()
        unknown_roles = {r for ep in self.api_spec["endpoints"] for r in ep.get("required_roles", [])} - set(bp.roles)
        if unknown_roles:
            raise ValidationError(f"API contract references undefined roles: {', '.join(sorted(unknown_roles))}")
        spec = build_auth_spec(bp, self.api_spec)
        roles = ", ".join("%s (%d permissions)" % (r["role_name"], len(r["permissions"])) for r in spec["rbac_roles"])
        self.log(f"RBAC: {roles}; {len(spec['protected_endpoints'])} protected endpoints; PBKDF2-SHA256 + HS256 JWT")
        return spec

    def emit_code(self, output: AuthOutput) -> List[str]:
        return write_auth_files(build_blueprint(self.pm_data), self.project, self.api_spec)
