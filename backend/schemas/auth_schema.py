"""Minimal compatibility stub schema for AuthOutput."""

from typing import List, Any
from pydantic import BaseModel, Field


class PasswordSecurity(BaseModel):
    hashing_algorithm: str = "bcrypt"


class JWTStrategy(BaseModel):
    algorithm: str = "HS256"


class AuthOutput(BaseModel):
    project_name: str
    password_security: PasswordSecurity = Field(default_factory=PasswordSecurity)
    jwt_strategy: JWTStrategy = Field(default_factory=JWTStrategy)
    auth_endpoints: List[Any] = Field(default_factory=lambda: ["/login", "/register", "/token", "/refresh", "/logout"])
    rbac_roles: List[Any] = Field(default_factory=lambda: ["admin", "user"])
