"""Pydantic V2 schemas for Deploy Agent Output validation."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class DeployOutput(BaseModel):
    """Deploy Agent JSON output schema."""
    project_name: str = Field(..., description="Project name")
    deployment_target: str = Field(default="Docker", description="Deployment target e.g. Docker, Vercel, Render, AWS")
    container_status: str = Field(default="SUCCESS", description="Container build/run status e.g. SUCCESS, FAILED, PENDING")
    dockerfile_content: Optional[str] = Field(default=None, description="Generated Dockerfile content")
    docker_compose_content: Optional[str] = Field(default=None, description="Generated docker-compose.yml content")
    deployment_url: Optional[str] = Field(default=None, description="Live deployment URL if applicable")
    environment_variables_configured: List[str] = Field(default_factory=list, description="Configured environment variable keys")
    health_check_status: str = Field(default="HEALTHY", description="Deployment health status e.g. HEALTHY, UNHEALTHY, UNKNOWN")
    deployment_logs: List[str] = Field(default_factory=list, description="Deployment execution log lines")
