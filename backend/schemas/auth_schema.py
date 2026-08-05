"""Pydantic V2 schemas for Authentication Agent Output validation."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class PasswordSecuritySpec(BaseModel):
    """Password hashing and strength rules."""
    hashing_algorithm: str = Field(default="bcrypt", description="Hashing algorithm")
    bcrypt_rounds: int = Field(default=12, description="Bcrypt work factor / rounds")
    min_length: int = Field(default=8, description="Minimum password length")
    require_uppercase: bool = Field(default=True, description="Must contain uppercase letter")
    require_lowercase: bool = Field(default=True, description="Must contain lowercase letter")
    require_digit: bool = Field(default=True, description="Must contain digit")
    require_special_char: bool = Field(default=True, description="Must contain special character")


class JWTStrategySpec(BaseModel):
    """JWT Token authentication strategy configuration."""
    algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    access_token_expire_minutes: int = Field(default=30, description="Access token TTL in minutes")
    refresh_token_expire_days: int = Field(default=7, description="Refresh token TTL in days")
    secret_key_env_var: str = Field(default="JWT_SECRET_KEY", description="Environment variable name for secret key")
    token_type: str = Field(default="Bearer", description="HTTP Auth Scheme")
    claims: List[str] = Field(default_factory=lambda: ["sub", "exp", "iat", "role", "email"], description="JWT token claims")


class AuthEndpointSpec(BaseModel):
    """Auth related endpoint specification."""
    name: str = Field(..., description="Flow / Endpoint identifier e.g. register, login, refresh_token, logout, forgot_password, reset_password, verify_email")
    path: str = Field(..., description="API Path e.g. /api/auth/login")
    method: str = Field(..., description="HTTP Method e.g. POST")
    description: str = Field(..., description="Endpoint purpose and behavior")
    requires_authentication: bool = Field(default=False, description="Whether endpoint requires Bearer token")
    request_fields: List[str] = Field(default_factory=list, description="Fields required in request body")
    response_fields: List[str] = Field(default_factory=list, description="Fields returned in response body")


class RBACRoleSpec(BaseModel):
    """Role Based Access Control Role definition."""
    role_name: str = Field(..., description="Role name e.g. Admin, User, Moderator")
    description: str = Field(..., description="Role responsibilities")
    permissions: List[str] = Field(default_factory=list, description="Permissions granted to role e.g. read:tasks, write:tasks, delete:users")


class UserEntityRequirement(BaseModel):
    """Security field requirements for User entity."""
    required_fields: List[Dict[str, str]] = Field(
        default_factory=lambda: [
            {"name": "id", "type": "INTEGER", "description": "Primary key"},
            {"name": "email", "type": "VARCHAR(255)", "description": "Unique email address"},
            {"name": "hashed_password", "type": "VARCHAR(255)", "description": "Bcrypt hashed password"},
            {"name": "role", "type": "VARCHAR(50)", "description": "User RBAC role"},
            {"name": "is_active", "type": "BOOLEAN", "description": "Account active flag"},
            {"name": "is_superuser", "type": "BOOLEAN", "description": "Superuser flag"},
            {"name": "email_verified", "type": "BOOLEAN", "description": "Email verification status"},
            {"name": "created_at", "type": "TIMESTAMP", "description": "Account creation timestamp"}
        ],
        description="Fields mandatory on User model for security compliance"
    )


class SecurityMiddlewareSpec(BaseModel):
    """Middleware and headers configured for app security."""
    name: str = Field(..., description="Middleware name e.g. CORSMiddleware, RateLimitingMiddleware, SecurityHeadersMiddleware")
    description: str = Field(..., description="Purpose and security benefit")
    configuration: Dict[str, Any] = Field(default_factory=dict, description="Configuration options")


class AuthOutput(BaseModel):
    """Auth Agent JSON output schema."""
    project_name: str = Field(..., description="Project name")
    password_security: PasswordSecuritySpec = Field(default_factory=PasswordSecuritySpec, description="Password hashing policy")
    jwt_strategy: JWTStrategySpec = Field(default_factory=JWTStrategySpec, description="JWT strategy configuration")
    auth_endpoints: List[AuthEndpointSpec] = Field(default_factory=list, description="Authentication endpoints")
    rbac_roles: List[RBACRoleSpec] = Field(default_factory=list, description="Configured RBAC roles")
    user_entity_requirements: UserEntityRequirement = Field(default_factory=UserEntityRequirement, description="User model security fields")
    protected_endpoints: List[Dict[str, Any]] = Field(default_factory=list, description="Mapping of endpoints and required permissions")
    security_middlewares: List[SecurityMiddlewareSpec] = Field(default_factory=list, description="Security middlewares configuration")
    password_reset_workflow: Dict[str, Any] = Field(default_factory=dict, description="Password reset workflow steps")
    email_verification_workflow: Dict[str, Any] = Field(default_factory=dict, description="Email verification workflow steps")
