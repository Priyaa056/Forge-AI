"""Phase 5 Production Hardening & End-to-End Integration Test Suite."""

import json
import pytest
from pathlib import Path

from backend.services.pipeline import ForgePipeline, PipelineStage, AgentStatus
from backend.artifacts.artifact_manager import ArtifactManager
from backend.artifacts.artifact_store import LocalJsonArtifactStore
from backend.artifacts.artifact_schema import ArtifactStatus as StorageArtifactStatus
from backend.monitoring.logger import PipelineLogger, sanitize_secret
from backend.monitoring.execution_event import EventType
from backend.monitoring.query import MonitoringService
from backend.artifacts.rollback_manager import RollbackManager, RollbackDependencyError

from backend.schemas.pm_schema import PMOutput
from backend.schemas.ui_schema import UIOutput
from backend.schemas.backend_schema import BackendOutput
from backend.schemas.db_schema import DBOutput
from backend.schemas.auth_schema import AuthOutput
from backend.schemas.qa_schema import QAOutput
from backend.schemas.deploy_schema import DeployOutput


@pytest.fixture
def mock_pm_setup(tmp_path):
    """Utility fixture copying outputs/pm_output.json to temporary test directory."""
    pm_src = Path("outputs/pm_output.json")
    if pm_src.exists():
        (tmp_path / "pm_output.json").write_text(pm_src.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def test_e2e_full_7agent_pipeline_execution(mock_pm_setup):
    """Verify all 7 agents execute through ForgePipeline with ArtifactManager persistence and lineage tracking."""
    store = LocalJsonArtifactStore(storage_dir=str(mock_pm_setup / "artifacts"))
    art_mgr = ArtifactManager(store=store)
    logger_inst = PipelineLogger(log_dir=str(mock_pm_setup / "logs"))

    pipeline = ForgePipeline(
        user_prompt="Build end-to-end task manager app",
        project_id="proj_e2e_7agent",
        run_id="run_e2e_7agent",
        output_dir=str(mock_pm_setup),
        artifact_manager=art_mgr,
        pipeline_logger=logger_inst,
    )

    state = pipeline.run_pipeline()
    assert state.execution_status == AgentStatus.COMPLETED

    # Verify all 7 stages completed in state
    for stage in PipelineStage:
        assert state.agent_statuses[stage] == AgentStatus.COMPLETED
        assert stage.value in state.artifact_ids

    # Verify output JSON files exist
    for stage in PipelineStage:
        out_file = mock_pm_setup / f"{stage.value}_output.json"
        assert out_file.exists()

    # Verify ArtifactManager stored all 7 artifacts
    pm_art = art_mgr.get_artifact(state.artifact_ids["pm"])
    ui_art = art_mgr.get_artifact(state.artifact_ids["ui"])
    backend_art = art_mgr.get_artifact(state.artifact_ids["backend"])
    db_art = art_mgr.get_artifact(state.artifact_ids["db"])
    auth_art = art_mgr.get_artifact(state.artifact_ids["auth"])
    qa_art = art_mgr.get_artifact(state.artifact_ids["qa"])
    deploy_art = art_mgr.get_artifact(state.artifact_ids["deploy"])

    assert pm_art and pm_art.status == StorageArtifactStatus.COMPLETED
    assert ui_art and ui_art.status == StorageArtifactStatus.COMPLETED
    assert backend_art and backend_art.status == StorageArtifactStatus.COMPLETED
    assert db_art and db_art.status == StorageArtifactStatus.COMPLETED
    assert auth_art and auth_art.status == StorageArtifactStatus.COMPLETED
    assert qa_art and qa_art.status == StorageArtifactStatus.COMPLETED
    assert deploy_art and deploy_art.status == StorageArtifactStatus.COMPLETED

    # Verify complete Lineage Chain
    assert ui_art.input_artifacts == [pm_art.artifact_id]
    assert set(backend_art.input_artifacts) == {pm_art.artifact_id, ui_art.artifact_id}
    assert set(db_art.input_artifacts) == {pm_art.artifact_id, backend_art.artifact_id}
    assert set(auth_art.input_artifacts) == {pm_art.artifact_id, backend_art.artifact_id, db_art.artifact_id}
    assert set(qa_art.input_artifacts) == {pm_art.artifact_id, ui_art.artifact_id, backend_art.artifact_id, db_art.artifact_id, auth_art.artifact_id}
    assert set(deploy_art.input_artifacts) == {pm_art.artifact_id, ui_art.artifact_id, backend_art.artifact_id, db_art.artifact_id, auth_art.artifact_id, qa_art.artifact_id}


def test_e2e_pipeline_monitoring_correlation(mock_pm_setup):
    """Verify monitoring events correlation, metrics calculation, and logging across full execution."""
    logger_inst = PipelineLogger(log_dir=str(mock_pm_setup / "logs"))
    service = MonitoringService(logger_instance=logger_inst)

    pipeline = ForgePipeline(
        user_prompt="Monitoring correlation app",
        project_id="proj_mon_corr",
        run_id="run_mon_corr",
        output_dir=str(mock_pm_setup),
        pipeline_logger=logger_inst,
    )

    pipeline.run_pipeline()

    events = service.get_events_by_run_id("run_mon_corr")
    assert len(events) >= 23  # Started + Completed + 7*(Agent Started + Artifact Created + Agent Completed)

    event_types = [e.event_type for e in events]
    assert EventType.PIPELINE_STARTED in event_types
    assert EventType.PIPELINE_COMPLETED in event_types
    assert EventType.AGENT_STARTED in event_types
    assert EventType.AGENT_COMPLETED in event_types
    assert EventType.ARTIFACT_CREATED in event_types

    # Verify correlation fields
    for evt in events:
        assert evt.run_id == "run_mon_corr"
        assert evt.project_id == "proj_mon_corr"

    metrics = service.get_execution_metrics("run_mon_corr")
    assert metrics["pipeline_status"] == "COMPLETED"
    assert metrics["successful_agent_count"] == 7
    assert metrics["failed_agent_count"] == 0
    assert metrics["total_artifacts_created"] == 7
    assert metrics["total_pipeline_duration_ms"] >= 0.0


def test_e2e_pipeline_stage_failure_and_rollback_recovery(mock_pm_setup):
    """Verify middle stage failure handling, FAILED artifact recording, error event logging, and rollback recovery."""
    art_mgr = ArtifactManager(store=LocalJsonArtifactStore(storage_dir=str(mock_pm_setup / "artifacts")))
    logger_inst = PipelineLogger(log_dir=str(mock_pm_setup / "logs"))

    pipeline = ForgePipeline(
        user_prompt="Faulty pipeline recovery app",
        project_id="proj_fail_e2e",
        run_id="run_fail_e2e",
        output_dir=str(mock_pm_setup),
        artifact_manager=art_mgr,
        pipeline_logger=logger_inst,
    )

    # 1. Run PM and UI stage successfully
    pipeline.run_stage(PipelineStage.PM)
    pipeline.run_stage(PipelineStage.UI)
    pm_v1_id = pipeline.state.artifact_ids["pm"]

    # 2. Register failing backend handler
    def failing_backend(ctx):
        raise ValueError("Database connection failed for secret_key=AIzaSy1234567890123456789012345678901")

    pipeline.register_agent_handler(PipelineStage.BACKEND, failing_backend)

    # 3. Assert stage failure raises exception without swallowing
    with pytest.raises(ValueError) as exc_info:
        pipeline.run_stage(PipelineStage.BACKEND)

    assert "Database connection failed" in str(exc_info.value)
    assert pipeline.state.agent_statuses[PipelineStage.BACKEND] == AgentStatus.FAILED

    # Verify FAILED artifact recorded in ArtifactManager
    failed_art = art_mgr.get_artifact(pipeline.state.artifact_ids["backend"])
    assert failed_art is not None
    assert failed_art.status == StorageArtifactStatus.FAILED
    assert failed_art.content["error"] is not None

    # Verify AGENT_FAILED event logged and sanitized
    events = logger_inst.read_logs_from_file()
    agent_fail_evts = [e for e in events if e.event_type == EventType.AGENT_FAILED]
    assert len(agent_fail_evts) == 1
    fail_evt = agent_fail_evts[0]
    assert "AIzaSy1234567890123456789012345678901" not in fail_evt.error_message
    assert "[REDACTED_GEMINI_KEY]" in fail_evt.error_message

    # 4. Perform rollback recovery on PM stage with force=True
    rb_res = pipeline.rollback_stage(PipelineStage.PM, target_version=1, force=True)
    assert rb_res.status == "COMPLETED"
    assert rb_res.restored_version == 2
    assert pipeline.state.artifact_ids["pm"] == rb_res.restored_artifact_id


def test_e2e_secret_safety_audit(mock_pm_setup):
    """Verify that credentials and sensitive tokens are sanitized across all monitoring events and artifacts."""
    logger_inst = PipelineLogger(log_dir=str(mock_pm_setup / "logs"))

    secret_key = "AIzaSy1234567890123456789012345678901"
    raw_prompt = f"Build app with GOOGLE_API_KEY={secret_key} password: secretpass123"

    pipeline = ForgePipeline(
        user_prompt=raw_prompt,
        project_id="proj_sec_audit",
        run_id="run_sec_audit",
        output_dir=str(mock_pm_setup),
        pipeline_logger=logger_inst,
    )

    pipeline.run_stage(PipelineStage.PM)

    events = logger_inst.read_logs_from_file()
    for evt in events:
        if evt.message:
            assert secret_key not in evt.message
            assert "secretpass123" not in evt.message
        if evt.error_message:
            assert secret_key not in evt.error_message
            assert "secretpass123" not in evt.error_message


def test_e2e_repeated_pipeline_execution_versioning(mock_pm_setup):
    """Verify repeated pipeline executions increment version numbers cleanly without corrupting history."""
    art_mgr = ArtifactManager(store=LocalJsonArtifactStore(storage_dir=str(mock_pm_setup / "artifacts")))

    # Run 1
    p1 = ForgePipeline(
        user_prompt="Run 1 Prompt",
        project_id="proj_repeat",
        run_id="run_repeat_1",
        output_dir=str(mock_pm_setup / "p1"),
        artifact_manager=art_mgr,
    )
    p1.run_stage(PipelineStage.PM)
    art_v1 = art_mgr.get_latest_artifact("proj_repeat", "pm")
    assert art_v1.version == 1

    # Run 2 on same project_id
    p2 = ForgePipeline(
        user_prompt="Run 2 Prompt",
        project_id="proj_repeat",
        run_id="run_repeat_2",
        output_dir=str(mock_pm_setup / "p2"),
        artifact_manager=art_mgr,
    )
    p2.run_stage(PipelineStage.PM)
    art_v2 = art_mgr.get_latest_artifact("proj_repeat", "pm")
    assert art_v2.version == 2

    # Verify both versions exist intact in storage
    all_versions = art_mgr.get_all_versions("proj_repeat", "pm")
    assert len(all_versions) == 2
    assert all_versions[0].version == 1
    assert all_versions[1].version == 2
