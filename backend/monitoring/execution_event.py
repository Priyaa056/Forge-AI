"""Structured Execution Event Model for Pipeline Monitoring."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Pipeline and Agent Event Types."""
    PIPELINE_STARTED = "PIPELINE_STARTED"
    PIPELINE_COMPLETED = "PIPELINE_COMPLETED"
    PIPELINE_FAILED = "PIPELINE_FAILED"
    AGENT_STARTED = "AGENT_STARTED"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    AGENT_FAILED = "AGENT_FAILED"
    ARTIFACT_CREATED = "ARTIFACT_CREATED"
    ARTIFACT_FAILED = "ARTIFACT_FAILED"
    ROLLBACK_STARTED = "ROLLBACK_STARTED"
    ROLLBACK_COMPLETED = "ROLLBACK_COMPLETED"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"


class ExecutionEvent(BaseModel):
    """Pydantic model representing a single structured pipeline execution event."""
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    run_id: str
    project_id: str
    event_type: EventType
    agent_name: Optional[str] = None
    pipeline_stage: Optional[str] = None
    status: Optional[str] = None
    duration_ms: Optional[float] = None
    artifact_id: Optional[str] = None
    input_artifact_ids: Optional[List[str]] = None
    message: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
