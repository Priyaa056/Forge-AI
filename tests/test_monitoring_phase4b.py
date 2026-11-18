"""Phase 4B Test Suite: Monitoring & Observability Integration for FORGE AI."""

import json
import pytest
from pathlib import Path

from backend.monitoring.execution_event import ExecutionEvent, EventType
from backend.monitoring.logger import PipelineLogger, sanitize_secret
from backend.monitoring.query import MonitoringService
from backend.services.pipeline import ForgePipeline, PipelineStage, AgentStatus


@pytest.fixture
def mock_pm_file(tmp_path):
    """Utility fixture to create a valid pm_output.json file in tmp_path."""
    pm_src = Path("outputs/pm_output.json")
    if pm_src.exists():
        (tmp_path / "pm_output.json").write_text(pm_src.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path














def test_persistence_and_reload(tmp_path):
    """Test reading back events from JSONL log file using a newly instantiated PipelineLogger & MonitoringService."""
    log_dir = tmp_path / "logs"
    logger1 = PipelineLogger(log_dir=str(log_dir))

    # Log initial events
    logger1.log_pipeline_started("run_p1", "proj_p1")
    logger1.log_agent_completed("run_p1", "proj_p1", "pm", "pm", 12.5, artifact_id="art_pm_1")
    logger1.log_pipeline_completed("run_p1", "proj_p1", 15.0)

    # Create a fresh logger2 pointing to the same log_dir
    logger2 = PipelineLogger(log_dir=str(log_dir))
    reloaded_events = logger2.read_logs_from_file()

    assert len(reloaded_events) == 3
    assert reloaded_events[0].event_type == EventType.PIPELINE_STARTED
    assert reloaded_events[1].artifact_id == "art_pm_1"
    assert reloaded_events[2].event_type == EventType.PIPELINE_COMPLETED

    # Query metrics on reloaded service
    service2 = MonitoringService(log_dir=str(log_dir))
    metrics = service2.get_execution_metrics("run_p1")
    assert metrics["pipeline_status"] == "COMPLETED"
    assert metrics["successful_agent_count"] == 1
    assert metrics["total_pipeline_duration_ms"] == 15.0


def test_secret_sanitization_on_new_paths():
    """Test secret sanitization for sensitive credentials across diverse formats."""
    # Gemini Key
    gemini_msg = "Error connecting with AIzaSy39847293847293847293847293847"
    assert "[REDACTED_GEMINI_KEY]" in sanitize_secret(gemini_msg)

    # OpenAI Key
    openai_msg = "Invalid sk-abcdef1234567890abcdef1234567890 key"
    assert "[REDACTED_OPENAI_KEY]" in sanitize_secret(openai_msg)

    # Bearer token
    bearer_msg = "Header Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    assert "Bearer [REDACTED_TOKEN]" in sanitize_secret(bearer_msg)

    # Key-value secret assignments
    kv_msg = "db_password=mysecretpassword123; api_token='supertoken999'"
    sanitized_kv = sanitize_secret(kv_msg)
    assert "mysecretpassword123" not in sanitized_kv
    assert "supertoken999" not in sanitized_kv
    assert "db_password=[REDACTED]" in sanitized_kv
    assert "api_token='[REDACTED]'" in sanitized_kv

    # Database connection URI
    db_uri = "postgresql://dbuser:supersecretpass@localhost:5432/forgedb"
    sanitized_db = sanitize_secret(db_uri)
    assert "supersecretpass" not in sanitized_db
    assert "postgresql://dbuser:[REDACTED]@localhost:5432/forgedb" in sanitized_db


