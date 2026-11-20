"""Artifact Schema definitions for FORGE AI Multi-Agent System."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class ArtifactStatus(str, Enum):
    """Artifact lifecycle status."""
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Artifact(BaseModel):
    """Structured, versioned artifact produced or consumed by FORGE AI agents."""

    model_config = ConfigDict(extra="ignore")

    artifact_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the artifact"
    )
    project_id: str = Field(
        ...,
        description="Unique identifier for the target project"
    )
    run_id: str = Field(
        ...,
        description="Unique execution run identifier"
    )
    agent_name: str = Field(
        ...,
        description="Name of the agent generating this artifact (e.g. pm, ui, backend)"
    )
    artifact_type: str = Field(
        ...,
        description="Type/Schema descriptor of artifact payload (e.g. PMOutput, UIOutput)"
    )
    version: int = Field(
        default=1,
        ge=1,
        description="Version number for this agent artifact within the project"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp of creation"
    )
    input_artifacts: List[str] = Field(
        default_factory=list,
        description="List of artifact_ids consumed as inputs to produce this artifact"
    )
    status: ArtifactStatus = Field(
        default=ArtifactStatus.COMPLETED,
        description="Execution/production status of the artifact"
    )
    content: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured data payload of the artifact"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context, timing, token usage, or custom tags"
    )
