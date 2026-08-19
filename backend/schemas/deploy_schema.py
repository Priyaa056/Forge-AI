"""Pydantic V2 schemas for Deploy Agent Output validation."""

from typing import List, Optional, Dict
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
    backend_image: str = Field(default="forge-backend:latest", description="Backend docker image tag")
    frontend_image: str = Field(default="forge-frontend:latest", description="Frontend docker image tag")
    db_image: str = Field(default="postgres:15-alpine", description="Database docker image tag")
    compose_file: str = Field(default="docker-compose.yml", description="Docker compose file path")
    exposed_ports: Dict[str, int] = Field(default_factory=lambda: {"backend": 8000, "frontend": 3000, "postgres": 5432}, description="Exposed service ports")


class DeployOutput(BaseModel):
    """Deploy Agent JSON output schema."""
    status: str = Field(..., description="Deployment status: 'success', 'failed', or 'pending'")
    environment: str = Field(default="development", description="Target environment: 'development', 'staging', 'production'")
    live_url: Optional[str] = Field(default=None, description="Accessible live deployment URL")
    docker_config: Optional[DockerConfigSpec] = Field(default_factory=DockerConfigSpec, description="Docker packaging configuration")
    health_checks: List[HealthCheckResult] = Field(default_factory=list, description="Automated health check verification results")
    deployment_timestamp: Optional[str] = Field(default=None, description="ISO timestamp of deployment execution")
    logs: List[str] = Field(default_factory=list, description="Deployment process logs")
    affected_component: Optional[str] = Field(default=None, description="Affected component if deployment failed")
