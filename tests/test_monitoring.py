"""Test suite for Phase 4A: Structured Logging & Pipeline Monitoring Foundation."""

import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from backend.monitoring.execution_event import ExecutionEvent, EventType
from backend.monitoring.logger import PipelineLogger, sanitize_secret
from backend.services.pipeline import ForgePipeline, PipelineStage, AgentStatus


def test_structured_event_creation():
    """Test 1: Structured ExecutionEvent model validation and default fields."""
    event = ExecutionEvent(
        run_id="run_test123",
        project_id="proj_test123",
        event_type=EventType.AGENT_STARTED,
        agent_name="pm",
        pipeline_stage="pm",
        status="RUNNING",
    )
    assert event.event_id.startswith("evt_")
    assert event.timestamp is not None
    assert event.run_id == "run_test123"
    assert event.project_id == "proj_test123"
    assert event.event_type == EventType.AGENT_STARTED
    assert event.agent_name == "pm"
    assert event.pipeline_stage == "pm"


def test_secret_sanitization():
    """Test 14: Sensitive values sanitization in messages and logs."""
    raw_secret_key = "AIzaSy1234567890123456789012345678901"
    raw_error_msg = f"Failed connection using GOOGLE_API_KEY={raw_secret_key} password: secret123"

    sanitized = sanitize_secret(raw_error_msg)
    assert raw_secret_key not in sanitized
    assert "[REDACTED_GEMINI_KEY]" in sanitized
    assert "secret123" not in sanitized
    assert "password=[REDACTED]" in sanitized

    # Test token & Bearer
    token_str = "Bearer eyJhbGciOiJIUzI1Ni..."
    assert "eyJhbGci" not in sanitize_secret(token_str)
    assert "Bearer [REDACTED_TOKEN]" in sanitize_secret(token_str)








