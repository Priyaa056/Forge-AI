"""Pydantic V2 schemas for the Deploy Agent output (``deployment_report.json``)."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class HealthCheckResult(BaseModel):
    """Result of a single service/endpoint health check."""
    endpoint: str = Field(..., description="Endpoint or service checked e.g. /health")
    status_code: int = Field(..., description="HTTP status code returned")
    status: str = Field(..., description="Health status: 'healthy' or 'unhealthy'")
    response_time_ms: float = Field(default=0.0, description="Latency in milliseconds")
    message: Optional[str] = Field(default=None, description="Health check details or message")


class DockerConfigSpec(BaseModel):
    """Docker configuration specification."""
    backend_image: str = Field(default="forge-backend:latest")
    frontend_image: str = Field(default="forge-frontend:latest")
    db_image: str = Field(default="postgres:16-alpine")
    compose_file: str = Field(default="docker-compose.yml")
    exposed_ports: Dict[str, int] = Field(default_factory=lambda: {"backend": 8000, "frontend": 8080, "postgres": 5432})


class ReadinessCheck(BaseModel):
    name: str
    status: str = Field(..., description="passed | failed | skipped")
    details: str = ""


class DeployOutput(BaseModel):
    """Deploy Agent JSON output schema."""
    project_name: Optional[str] = Field(default=None)
    status: str = Field(..., description="Deployment readiness: 'success' or 'failed'")
    environment: str = Field(default="development", description="Target environment")
    live_url: Optional[str] = Field(default=None, description="URL used for the live health check (process is stopped afterwards)")
    docker_config: Optional[DockerConfigSpec] = Field(default_factory=DockerConfigSpec)
    health_checks: List[HealthCheckResult] = Field(default_factory=list, description="Live health check results")
    readiness_checks: List[ReadinessCheck] = Field(default_factory=list, description="Configuration validation results")
    required_env_vars: List[str] = Field(default_factory=list)
    docker_available: bool = Field(default=False, description="Whether the Docker CLI was found on this machine")
    container_build_verified: bool = Field(default=False, description="True only if docker images were actually built")
    deployment_ready: bool = Field(default=False)
    deployment_timestamp: Optional[str] = Field(default=None)
    instructions: List[str] = Field(default_factory=list, description="How to run/deploy the generated app")
    logs: List[str] = Field(default_factory=list, description="Deployment process logs")
    affected_component: Optional[str] = Field(default=None, description="Affected component if deployment failed")
    summary: Optional[str] = Field(default=None, description="Human readable readiness summary")
