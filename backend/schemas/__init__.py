"""Schemas package for all FORGE AI Agents (PM, UI, Backend, DB, Auth, QA, Deploy)."""

from .pm_schema import PMOutput, DatabaseEntity, EntityField, TechStack
from .ui_schema import UIOutput, UIPage, UIComponent, UIRoute, UILayout, UIForm, APIRequirement, StylingRequirements
from .backend_schema import BackendOutput, EndpointSpec, RequestSchemaSpec, ResponseSchemaSpec, ServiceLayerSpec, RepositoryLayerSpec
from .db_schema import DBOutput, TableSpec, ColumnSpec, ForeignKeySpec, RelationshipSpec, IndexSpec, AlembicMetadata
from .auth_schema import AuthOutput, AuthEndpointSpec, RBACRoleSpec, PasswordSecuritySpec, JWTStrategySpec, UserEntityRequirement
from .qa_schema import QAOutput, QAErrorDetail, QAError
from .deploy_schema import DeployOutput, HealthCheckResult, DockerConfigSpec

__all__ = [
    "PMOutput", "DatabaseEntity", "EntityField", "TechStack",
    "UIOutput", "UIPage", "UIComponent", "UIRoute", "UILayout", "UIForm", "APIRequirement", "StylingRequirements",
    "BackendOutput", "EndpointSpec", "RequestSchemaSpec", "ResponseSchemaSpec", "ServiceLayerSpec", "RepositoryLayerSpec",
    "DBOutput", "TableSpec", "ColumnSpec", "ForeignKeySpec", "RelationshipSpec", "IndexSpec", "AlembicMetadata",
    "AuthOutput", "AuthEndpointSpec", "RBACRoleSpec", "PasswordSecuritySpec", "JWTStrategySpec", "UserEntityRequirement",
    "QAOutput", "QAErrorDetail", "QAError",
    "DeployOutput", "HealthCheckResult", "DockerConfigSpec",
]
