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


def test_pipeline_started_completed_events_and_duration(tmp_path):
    """Test 2, 4, 6, 8, 9, 10: PIPELINE_STARTED, AGENT_STARTED, AGENT_COMPLETED, PIPELINE_COMPLETED events and duration."""
    # Copy pm_output.json for pipeline run
    pm_src = Path("outputs/pm_output.json")
    if pm_src.exists():
        (tmp_path / "pm_output.json").write_text(pm_src.read_text(encoding="utf-8"), encoding="utf-8")

    logger_inst = PipelineLogger(log_dir=str(tmp_path / "logs"))
    pipeline = ForgePipeline(
        user_prompt="Build monitoring app",
        project_id="proj_mon_1",
        run_id="run_mon_1",
        output_dir=str(tmp_path),
        pipeline_logger=logger_inst,
    )

    state = pipeline.run_pipeline()
    assert state.execution_status == AgentStatus.COMPLETED

    events = logger_inst.read_logs_from_file()
    assert len(events) > 0

    event_types = [e.event_type for e in events]
    assert EventType.PIPELINE_STARTED in event_types
    assert EventType.PIPELINE_COMPLETED in event_types
    assert EventType.AGENT_STARTED in event_types
    assert EventType.AGENT_COMPLETED in event_types
    assert EventType.ARTIFACT_CREATED in event_types

    start_evt = [e for e in events if e.event_type == EventType.PIPELINE_STARTED][0]
    assert start_evt.run_id == "run_mon_1"
    assert start_evt.project_id == "proj_mon_1"

    comp_evt = [e for e in events if e.event_type == EventType.PIPELINE_COMPLETED][0]
    assert comp_evt.run_id == "run_mon_1"
    assert comp_evt.project_id == "proj_mon_1"
    assert comp_evt.duration_ms is not None
    assert comp_evt.duration_ms >= 0.0

    # Verify agent completed events have duration_ms recorded
    agent_comp_evts = [e for e in events if e.event_type == EventType.AGENT_COMPLETED]
    assert len(agent_comp_evts) == 7
    for evt in agent_comp_evts:
        assert evt.duration_ms is not None
        assert evt.duration_ms >= 0.0
        assert evt.run_id == "run_mon_1"
        assert evt.project_id == "proj_mon_1"


def test_agent_and_pipeline_failed_events(tmp_path):
    """Test 5, 7, 13: AGENT_FAILED and PIPELINE_FAILED events generated without swallowing exception."""
    logger_inst = PipelineLogger(log_dir=str(tmp_path / "logs"))
    pipeline = ForgePipeline(
        user_prompt="Faulty app",
        project_id="proj_fail_1",
        run_id="run_fail_1",
        output_dir=str(tmp_path),
        pipeline_logger=logger_inst,
    )

    def failing_backend_handler(ctx):
        raise ValueError("Database connection failed with secret_key=12345")

    pipeline.register_agent_handler(PipelineStage.BACKEND, failing_backend_handler)

    # First PM stage succeeds
    pipeline.run_stage(PipelineStage.PM)

    # UI stage succeeds
    pipeline.run_stage(PipelineStage.UI)

    # Backend stage fails - exception must NOT be swallowed by run_stage
    with pytest.raises(ValueError) as exc_info:
        pipeline.run_stage(PipelineStage.BACKEND)

    assert "Database connection failed" in str(exc_info.value)

    events = logger_inst.read_logs_from_file()
    agent_fail_evts = [e for e in events if e.event_type == EventType.AGENT_FAILED]
    assert len(agent_fail_evts) == 1

    fail_evt = agent_fail_evts[0]
    assert fail_evt.agent_name == "backend"
    assert fail_evt.pipeline_stage == "backend"
    assert fail_evt.status == "FAILED"
    assert fail_evt.error_type == "ValueError"
    assert "secret_key=12345" not in fail_evt.error_message
    assert "secret_key=[REDACTED]" in fail_evt.error_message

    # Also test full pipeline failure event
    pipeline2 = ForgePipeline(
        user_prompt="Faulty pipeline app",
        project_id="proj_fail_2",
        run_id="run_fail_2",
        output_dir=str(tmp_path / "pipe2"),
        pipeline_logger=logger_inst,
    )
    pipeline2.register_agent_handler(PipelineStage.UI, failing_backend_handler)
    pipeline2.run_pipeline()

    events2 = logger_inst.get_events(run_id="run_fail_2")
    pipeline_fail_evts = [e for e in events2 if e.event_type == EventType.PIPELINE_FAILED]
    assert len(pipeline_fail_evts) == 1
    p_fail_evt = pipeline_fail_evts[0]
    assert p_fail_evt.status == "FAILED"
    assert p_fail_evt.duration_ms is not None


def test_artifact_id_and_input_lineage_correlation(tmp_path):
    """Test 11, 12, 16: Correlation of artifact_id and input_artifact_ids across agent events."""
    logger_inst = PipelineLogger(log_dir=str(tmp_path / "logs"))
    pipeline = ForgePipeline(
        user_prompt="Correlation app",
        output_dir=str(tmp_path),
        pipeline_logger=logger_inst,
    )

    pipeline.run_stage(PipelineStage.PM)
    pm_art_id = pipeline.state.artifact_ids["pm"]
    assert pm_art_id is not None

    pipeline.run_stage(PipelineStage.UI)
    ui_art_id = pipeline.state.artifact_ids["ui"]

    events = logger_inst.read_logs_from_file()
    ui_comp_evt = [e for e in events if e.event_type == EventType.AGENT_COMPLETED and e.agent_name == "ui"][0]

    assert ui_comp_evt.artifact_id == ui_art_id
    assert pm_art_id in ui_comp_evt.input_artifact_ids


def test_get_status_summary_extended(tmp_path):
    """Test 15: get_status_summary() backward compatibility and extended monitoring info."""
    pipeline = ForgePipeline(
        user_prompt="Summary app",
        project_id="proj_sum",
        run_id="run_sum",
        output_dir=str(tmp_path),
    )

    pipeline.run_stage(PipelineStage.PM)
    summary = pipeline.get_status_summary()

    # Original fields preserved
    assert summary["project_id"] == "proj_sum"
    assert summary["run_id"] == "run_sum"
    assert summary["user_prompt"] == "Summary app"
    assert summary["execution_status"] == AgentStatus.PENDING.value
    assert "agent_statuses" in summary
    assert summary["agent_statuses"]["pm"] == AgentStatus.COMPLETED
    assert "artifact_ids" in summary
    assert "completed_stages" in summary
    assert summary["completed_stages"] == ["pm"]

    # Extended monitoring fields present
    assert "total_duration_ms" in summary
    assert summary["total_duration_ms"] >= 0.0
    assert summary["successful_agent_count"] == 1
    assert summary["failed_agent_count"] == 0
    assert "agents" in summary
    assert "pm" in summary["agents"]
    assert summary["agents"]["pm"]["status"] == AgentStatus.COMPLETED.value
    assert summary["agents"]["pm"]["duration_ms"] is not None
    assert summary["agents"]["pm"]["artifact_id"] == pipeline.state.artifact_ids["pm"]
