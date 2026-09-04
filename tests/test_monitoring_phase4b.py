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


def test_query_events_by_run_id_and_project_id(mock_pm_file):
    """Test retrieving execution events by run_id and project_id."""
    log_dir = mock_pm_file / "logs"
    logger_inst = PipelineLogger(log_dir=str(log_dir))
    service = MonitoringService(logger_instance=logger_inst)

    pipeline = ForgePipeline(
        user_prompt="Run ID query test",
        project_id="proj_query_1",
        run_id="run_query_1",
        output_dir=str(mock_pm_file),
        pipeline_logger=logger_inst,
    )
    pipeline.run_stage(PipelineStage.PM)

    run_events = service.get_events_by_run_id("run_query_1")
    assert len(run_events) >= 3  # PIPELINE_STARTED/AGENT_STARTED, ARTIFACT_CREATED, AGENT_COMPLETED
    assert all(e.run_id == "run_query_1" for e in run_events)

    proj_events = service.get_events_by_project_id("proj_query_1")
    assert len(proj_events) == len(run_events)
    assert all(e.project_id == "proj_query_1" for e in proj_events)

    non_existent = service.get_events_by_run_id("non_existent_run")
    assert len(non_existent) == 0


def test_query_events_by_agent_and_stage(mock_pm_file):
    """Test retrieving execution events filtered by agent_name and pipeline_stage."""
    logger_inst = PipelineLogger(log_dir=str(mock_pm_file / "logs"))
    service = logger_inst.get_query_service()

    pipeline = ForgePipeline(
        user_prompt="Agent query test",
        project_id="proj_agent_1",
        run_id="run_agent_1",
        output_dir=str(mock_pm_file),
        pipeline_logger=logger_inst,
    )
    pipeline.run_stage(PipelineStage.PM)
    pipeline.run_stage(PipelineStage.UI)

    pm_events = service.get_events_by_agent("pm")
    assert len(pm_events) > 0
    assert all(e.agent_name == "pm" for e in pm_events)

    ui_stage_events = service.get_events_by_stage("ui")
    assert len(ui_stage_events) > 0
    assert all(e.pipeline_stage == "ui" for e in ui_stage_events)


def test_filtering_failed_events(mock_pm_file):
    """Test filtering failed events across pipeline runs."""
    logger_inst = PipelineLogger(log_dir=str(mock_pm_file / "logs"))
    service = MonitoringService(logger_instance=logger_inst)

    pipeline = ForgePipeline(
        user_prompt="Failing agent test",
        project_id="proj_fail_query",
        run_id="run_fail_query",
        output_dir=str(mock_pm_file),
        pipeline_logger=logger_inst,
    )

    def bad_handler(ctx):
        raise RuntimeError("Simulated failure in backend agent")

    pipeline.register_agent_handler(PipelineStage.BACKEND, bad_handler)
    pipeline.run_stage(PipelineStage.PM)

    with pytest.raises(RuntimeError):
        pipeline.run_stage(PipelineStage.BACKEND)

    failed_evts = service.get_failed_events(run_id="run_fail_query")
    assert len(failed_evts) >= 2  # ARTIFACT_FAILED and AGENT_FAILED

    event_types = [e.event_type for e in failed_evts]
    assert EventType.ARTIFACT_FAILED in event_types
    assert EventType.AGENT_FAILED in event_types
    assert failed_evts[0].error_type == "RuntimeError"


def test_execution_metrics_calculation(mock_pm_file):
    """Test metric calculation for successful and failed pipeline runs."""
    logger_inst = PipelineLogger(log_dir=str(mock_pm_file / "logs"))
    service = logger_inst.get_query_service()

    pipeline = ForgePipeline(
        user_prompt="Metrics test app",
        project_id="proj_metrics_1",
        run_id="run_metrics_1",
        output_dir=str(mock_pm_file),
        pipeline_logger=logger_inst,
    )
    pipeline.run_pipeline()

    metrics = service.get_execution_metrics(run_id="run_metrics_1")
    assert metrics["pipeline_status"] == "COMPLETED"
    assert metrics["successful_agent_count"] == 7
    assert metrics["failed_agent_count"] == 0
    assert metrics["total_artifacts_created"] == 7
    assert metrics["failed_artifacts"] == 0
    assert metrics["total_pipeline_duration_ms"] >= 0.0
    assert "pm" in metrics["per_agent_duration_ms"]
    assert "deploy" in metrics["per_agent_duration_ms"]
    assert metrics["latest_event_type"] == EventType.PIPELINE_COMPLETED.value
    assert metrics["latest_event_timestamp"] is not None


def test_monitoring_summary_extended(mock_pm_file):
    """Test get_status_summary() extended monitoring metrics."""
    pipeline = ForgePipeline(
        user_prompt="Summary test",
        project_id="proj_sum_4b",
        run_id="run_sum_4b",
        output_dir=str(mock_pm_file),
    )
    pipeline.run_stage(PipelineStage.PM)

    summary = pipeline.get_status_summary()
    assert summary["project_id"] == "proj_sum_4b"
    assert summary["run_id"] == "run_sum_4b"
    assert summary["artifact_count"] == 1
    assert summary["failed_artifact_count"] == 0
    assert summary["latest_event_type"] == EventType.AGENT_COMPLETED.value
    assert summary["latest_event_timestamp"] is not None
    assert summary["monitoring_status"] == "ACTIVE"
    assert summary["monitoring status"] == "ACTIVE"


def test_event_correlation_and_lineage(mock_pm_file):
    """Verify event correlation across run_id, project_id, agent_name, stage, artifact_id, and input_artifact_ids."""
    logger_inst = PipelineLogger(log_dir=str(mock_pm_file / "logs"))
    pipeline = ForgePipeline(
        user_prompt="Correlation test",
        project_id="proj_corr",
        run_id="run_corr",
        output_dir=str(mock_pm_file),
        pipeline_logger=logger_inst,
    )
    pipeline.run_stage(PipelineStage.PM)
    pm_art_id = pipeline.state.artifact_ids["pm"]

    pipeline.run_stage(PipelineStage.UI)
    ui_art_id = pipeline.state.artifact_ids["ui"]

    events = logger_inst.get_query_service().get_events_by_run_id("run_corr")
    ui_created_evt = [e for e in events if e.event_type == EventType.ARTIFACT_CREATED and e.agent_name == "ui"][0]

    assert ui_created_evt.run_id == "run_corr"
    assert ui_created_evt.project_id == "proj_corr"
    assert ui_created_evt.pipeline_stage == "ui"
    assert ui_created_evt.artifact_id == ui_art_id
    assert pm_art_id in ui_created_evt.input_artifact_ids


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


def test_backward_compatibility(mock_pm_file):
    """Verify that existing ForgePipeline behavior remains completely unbroken."""
    pipeline = ForgePipeline(
        user_prompt="Backward compatibility test",
        output_dir=str(mock_pm_file),
    )
    pm_out = pipeline.run_stage(PipelineStage.PM)
    assert pm_out is not None
    assert hasattr(pipeline, "monitoring_service")

    summary = pipeline.get_status_summary()
    assert "completed_stages" in summary
    assert "agent_statuses" in summary
    assert "artifact_ids" in summary
    assert summary["completed_stages"] == ["pm"]
