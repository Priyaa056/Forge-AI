"""Authentication Agent for FORGE AI platform."""

import json
from typing import Dict, Any, Optional, List
from pathlib import Path

from backend.agents.base_agent import BaseAgent
from backend.schemas.pm_schema import PMOutput
from backend.schemas.backend_schema import BackendOutput
from backend.schemas.db_schema import DBOutput
from backend.schemas.auth_schema import AuthOutput
from backend.exceptions import MissingInputError, ValidationError, GenerationError


class AuthAgent(BaseAgent[AuthOutput]):
    """Agent responsible for generating JWT, Bcrypt, RBAC, and Auth Workflow specifications."""

    def __init__(self,
                 pm_output_path: str = "outputs/pm_output.json",
                 backend_output_path: str = "outputs/backend_output.json",
                 db_output_path: str = "outputs/db_output.json",
                 output_filepath: str = "outputs/auth_output.json"):
        super().__init__(output_schema_cls=AuthOutput, output_filepath=output_filepath)
        self.pm_output_path = pm_output_path
        self.backend_output_path = backend_output_path
        self.db_output_path = db_output_path
        self.pm_data: Optional[PMOutput] = None
        self.backend_data: Optional[BackendOutput] = None
        self.db_data: Optional[DBOutput] = None

    def load_inputs(self) -> None:
        """Load and validate PM, Backend, and DB specifications."""
        raw_pm = self.read_json_file(self.pm_output_path)
        try:
            self.pm_data = PMOutput.model_validate(raw_pm)
        except Exception as e:
            raise ValidationError(f"Invalid pm_output.json format: {e}")

        raw_backend = self.read_json_file(self.backend_output_path)
        try:
            self.backend_data = BackendOutput.model_validate(raw_backend)
        except Exception as e:
            raise ValidationError(f"Invalid backend_output.json format: {e}")

        raw_db = self.read_json_file(self.db_output_path)
        try:
            self.db_data = DBOutput.model_validate(raw_db)
        except Exception as e:
            raise ValidationError(f"Invalid db_output.json format: {e}")

    def generate(self) -> Dict[str, Any]:
        """Generate Authentication specification using LLM or rule-based fallback.

        Failure modes:
        - LLM API unavailable / network error → falls back to rule-based generator (safe, intended).
        - LLM returns malformed JSON or output that fails the Pydantic schema → raises
          GenerationError so the calling pipeline is explicitly notified (never silently replaced).
        """
        if not self.pm_data or not self.backend_data or not self.db_data:
            raise GenerationError("Inputs not loaded. Call load_inputs() first.")

        model = self.get_gemini_model()
        if model:
            # --- Phase 1: LLM API call -------------------------------------------------
            # A network/auth/quota failure is an infrastructure problem; fall back safely.
            llm_text: str | None = None
            try:
                prompt = self._build_prompt()
                response = model.generate_content(prompt)
                llm_text = response.text.strip()
            except Exception as e:
                self.logger.warning(
                    f"LLM API call failed ({e}). Falling back to rule-based generator."
                )

            # --- Phase 2: Output validation --------------------------------------------
            # The LLM responded — validate strictly. Do NOT fall back on bad output;
            # the caller must know the LLM produced unusable data.
            if llm_text is not None:
                return self.parse_and_validate_llm_output(llm_text)

        return self._generate_fallback()

    def _build_prompt(self) -> str:
        """Build structured LLM prompt for authentication spec generation."""
        return f"""
You are a Senior Security Engineer and Auth Architect AI.
Generate a JWT + Bcrypt Authentication specification JSON for the project '{self.pm_data.project_name}'.

STRICT RULES:
- Return ONLY valid raw JSON. No markdown formatting.
- Password MUST NEVER be stored in plain text.
- Output MUST conform to AuthOutput schema.
"""

    def _generate_fallback(self) -> Dict[str, Any]:
        """Dynamic rule-based generator for JWT, Bcrypt, RBAC, Security Middlewares, and Workflows."""
        project_name = self.pm_data.project_name

        # Protected endpoints extraction from backend output
        protected_endpoints: List[Dict[str, Any]] = []
        if self.backend_data:
            for ep in self.backend_data.endpoints:
                if ep.requires_auth:
                    protected_endpoints.append({
                        "path": ep.path,
                        "method": ep.method,
                        "required_roles": ep.required_roles or ["user"],
                        "required_permissions": [f"{ep.method.lower()}:{ep.tags[0].lower() if ep.tags else 'resource'}"]
                    })

        return {
            "project_name": project_name,
            "password_security": {
                "hashing_algorithm": "bcrypt",
                "bcrypt_rounds": 12,
                "min_length": 8,
                "require_uppercase": True,
                "require_lowercase": True,
                "require_digit": True,
                "require_special_char": True
            },
            "jwt_strategy": {
                "algorithm": "HS256",
                "access_token_expire_minutes": 30,
                "refresh_token_expire_days": 7,
                "secret_key_env_var": "JWT_SECRET_KEY",
                "token_type": "Bearer",
                "claims": ["sub", "exp", "iat", "role", "email"]
            },
            "auth_endpoints": [
                {
                    "name": "register",
                    "path": "/api/auth/register",
                    "method": "POST",
                    "description": "User registration flow creating new user account with hashed password.",
                    "requires_authentication": False,
                    "request_fields": ["email", "username", "password"],
                    "response_fields": ["id", "email", "username", "role", "created_at"]
                },
                {
                    "name": "login",
                    "path": "/api/auth/login",
                    "method": "POST",
                    "description": "User login flow verifying credentials and issuing JWT access & refresh tokens.",
                    "requires_authentication": False,
                    "request_fields": ["email", "password"],
                    "response_fields": ["access_token", "refresh_token", "token_type", "expires_in"]
                },
                {
                    "name": "refresh_token",
                    "path": "/api/auth/refresh",
                    "method": "POST",
                    "description": "Refresh token endpoint issuing new access token upon valid refresh token.",
                    "requires_authentication": False,
                    "request_fields": ["refresh_token"],
                    "response_fields": ["access_token", "token_type", "expires_in"]
                },
                {
                    "name": "logout",
                    "path": "/api/auth/logout",
                    "method": "POST",
                    "description": "Logout endpoint revoking / blacklisting active access & refresh tokens.",
                    "requires_authentication": True,
                    "request_fields": [],
                    "response_fields": ["message"]
                },
                {
                    "name": "forgot_password",
                    "path": "/api/auth/forgot-password",
                    "method": "POST",
                    "description": "Request password reset email containing secure reset token.",
                    "requires_authentication": False,
                    "request_fields": ["email"],
                    "response_fields": ["message"]
                },
                {
                    "name": "reset_password",
                    "path": "/api/auth/reset-password",
                    "method": "POST",
                    "description": "Reset password using valid reset token.",
                    "requires_authentication": False,
                    "request_fields": ["token", "new_password"],
                    "response_fields": ["message"]
                },
                {
                    "name": "verify_email",
                    "path": "/api/auth/verify-email",
                    "method": "GET",
                    "description": "Verify email address using token sent via email.",
                    "requires_authentication": False,
                    "request_fields": ["token"],
                    "response_fields": ["message"]
                }
            ],
            "rbac_roles": [
                {
                    "role_name": "Admin",
                    "description": "System Administrator with full management permissions.",
                    "permissions": ["read:all", "write:all", "delete:all", "manage:users", "manage:roles"]
                },
                {
                    "role_name": "User",
                    "description": "Standard registered user with access to application features.",
                    "permissions": ["read:own", "write:own", "delete:own"]
                },
                {
                    "role_name": "Guest",
                    "description": "Unauthenticated guest with read-only public access.",
                    "permissions": ["read:public"]
                }
            ],
            "user_entity_requirements": {
                "required_fields": [
                    {"name": "id", "type": "INTEGER", "description": "Primary key"},
                    {"name": "email", "type": "VARCHAR(255)", "description": "Unique email address"},
                    {"name": "hashed_password", "type": "VARCHAR(255)", "description": "Bcrypt hashed password"},
                    {"name": "role", "type": "VARCHAR(50)", "description": "User RBAC role"},
                    {"name": "is_active", "type": "BOOLEAN", "description": "Account active flag"},
                    {"name": "is_superuser", "type": "BOOLEAN", "description": "Superuser flag"},
                    {"name": "email_verified", "type": "BOOLEAN", "description": "Email verification status"},
                    {"name": "created_at", "type": "TIMESTAMP", "description": "Account creation timestamp"}
                ]
            },
            "protected_endpoints": protected_endpoints,
            "security_middlewares": [
                {
                    "name": "CORSMiddleware",
                    "description": "Controls allowed HTTP origins, methods, and credentials.",
                    "configuration": {"allow_origins": ["*"], "allow_credentials": True, "allow_methods": ["*"], "allow_headers": ["*"]}
                },
                {
                    "name": "RateLimitingMiddleware",
                    "description": "Limits API request rate per client IP to prevent brute-force attacks.",
                    "configuration": {"requests_per_minute": 60, "burst": 100}
                },
                {
                    "name": "SecurityHeadersMiddleware",
                    "description": "Adds standard HTTP security headers.",
                    "configuration": {
                        "X-Content-Type-Options": "nosniff",
                        "X-Frame-Options": "DENY",
                        "X-XSS-Protection": "1; mode=block",
                        "Strict-Transport-Security": "max-age=31536000; includeSubDomains"
                    }
                }
            ],
            "password_reset_workflow": {
                "step_1": "User submits email to /api/auth/forgot-password.",
                "step_2": "System generates short-lived secure JWT reset token (15 min expiry).",
                "step_3": "System dispatches password reset email with action URL containing token.",
                "step_4": "User submits new password and token to /api/auth/reset-password.",
                "step_5": "System validates token, hashes new password with bcrypt, updates user DB record, and invalidates reset token."
            },
            "email_verification_workflow": {
                "step_1": "Upon registration, user account is created with email_verified = False.",
                "step_2": "System generates email verification token (24 hour expiry).",
                "step_3": "System dispatches email containing verification link.",
                "step_4": "User clicks verification link triggering GET /api/auth/verify-email?token=...",
                "step_5": "System validates token and sets email_verified = True."
            }
        }


if __name__ == "__main__":
    agent = AuthAgent()
    agent.run()
