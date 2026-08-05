"""Pydantic V2 schemas for Backend Agent Output validation."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ParameterSpec(BaseModel):
    """Query or Path parameter definition."""
    name: str = Field(..., description="Parameter name")
    in_location: str = Field(..., description="Location: 'query' or 'path'")
    param_type: str = Field(default="str", description="Data type: str, int, bool, datetime")
    required: bool = Field(default=False, description="Whether parameter is required")
    default: Optional[Any] = Field(default=None, description="Default value if optional")
    description: Optional[str] = Field(default=None, description="Parameter documentation")


class SchemaFieldSpec(BaseModel):
    """Field specification inside a Pydantic Request/Response model."""
    name: str = Field(..., description="Field name")
    type: str = Field(..., description="Python type e.g. int, str, datetime, Optional[str]")
    required: bool = Field(default=True, description="Whether field is required")
    default: Optional[Any] = Field(default=None, description="Default value")
    validation_rules: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Pydantic validation constraints")


class RequestSchemaSpec(BaseModel):
    """Request Pydantic model specification."""
    name: str = Field(..., description="Model class name e.g. TaskCreate")
    fields: List[SchemaFieldSpec] = Field(default_factory=list, description="Fields contained in request schema")


class ResponseSchemaSpec(BaseModel):
    """Response Pydantic model specification."""
    name: str = Field(..., description="Model class name e.g. TaskResponse")
    status_code: int = Field(default=200, description="Default success HTTP status code")
    fields: List[SchemaFieldSpec] = Field(default_factory=list, description="Fields contained in response schema")


class EndpointSpec(BaseModel):
    """FastAPI Endpoint specification."""
    path: str = Field(..., description="API Path e.g. /api/tasks")
    method: str = Field(..., description="HTTP Method: GET, POST, PUT, DELETE, PATCH")
    summary: str = Field(..., description="Endpoint short summary")
    description: str = Field(..., description="Detailed endpoint behavior")
    operation_id: str = Field(..., description="Unique operation identifier e.g. create_task")
    tags: List[str] = Field(default_factory=list, description="OpenAPI tags for categorization")
    requires_auth: bool = Field(default=False, description="Requires authenticated user token")
    required_roles: List[str] = Field(default_factory=list, description="Roles permitted to call this endpoint")
    request_schema: Optional[RequestSchemaSpec] = Field(default=None, description="Request body Pydantic model")
    response_schema: ResponseSchemaSpec = Field(..., description="Response body Pydantic model")
    parameters: List[ParameterSpec] = Field(default_factory=list, description="Path and query parameters")
    business_logic_summary: str = Field(..., description="Description of business logic executed")
    is_file_upload: bool = Field(default=False, description="Whether endpoint handles multipart file uploads")


class ServiceMethodSpec(BaseModel):
    """Method in service layer."""
    name: str = Field(..., description="Method name e.g. get_user_tasks")
    params: List[str] = Field(default_factory=list, description="Method input parameters")
    return_type: str = Field(..., description="Return type hint")
    description: str = Field(..., description="Business rule / method functionality")


class ServiceLayerSpec(BaseModel):
    """Service layer class specification."""
    name: str = Field(..., description="Service class name e.g. TaskService")
    entity: str = Field(..., description="Target database entity")
    methods: List[ServiceMethodSpec] = Field(default_factory=list, description="Service layer methods")


class RepositoryMethodSpec(BaseModel):
    """Method in repository layer."""
    name: str = Field(..., description="Repository method name e.g. find_by_user_id")
    query_description: str = Field(..., description="SQL/ORM query operation description")
    return_type: str = Field(..., description="Return type hint")


class RepositoryLayerSpec(BaseModel):
    """Repository layer class specification."""
    name: str = Field(..., description="Repository class name e.g. TaskRepository")
    entity: str = Field(..., description="Target database entity")
    methods: List[RepositoryMethodSpec] = Field(default_factory=list, description="Data access methods")


class ErrorHandlerSpec(BaseModel):
    """HTTP Error Handler definition."""
    status_code: int = Field(..., description="HTTP status code e.g. 404, 400, 401")
    exception_type: str = Field(..., description="Exception class e.g. HTTPException, ResourceNotFoundException")
    detail: str = Field(..., description="Error message detail format")


class BackendOutput(BaseModel):
    """Backend Agent JSON output schema."""
    project_name: str = Field(..., description="Project name")
    architecture: str = Field(default="Clean Architecture (Controller-Service-Repository)", description="Backend architecture pattern")
    endpoints: List[EndpointSpec] = Field(default_factory=list, description="List of generated API endpoints")
    service_layer: List[ServiceLayerSpec] = Field(default_factory=list, description="Service layer specifications")
    repository_layer: List[RepositoryLayerSpec] = Field(default_factory=list, description="Repository layer specifications")
    global_dependencies: List[str] = Field(default_factory=list, description="FastAPI dependencies e.g. get_db, get_current_user")
    error_handlers: List[ErrorHandlerSpec] = Field(default_factory=list, description="Configured error handlers")
