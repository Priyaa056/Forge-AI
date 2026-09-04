"""Test suite for Phase 5: Rollback & Recovery System."""

import pytest
from pathlib import Path
from pydantic import BaseModel, Field

from backend.artifacts.artifact_schema import ArtifactStatus
from backend.artifacts.artifact_store import LocalJsonArtifactStore
from backend.artifacts.artifact_manager import ArtifactManager
from backend.artifacts.rollback_manager import (
    RollbackManager,
    RollbackResult,
    RollbackError,
    RollbackValidationError,
    RollbackDependencyError,
)
from backend.monitoring.logger import PipelineLogger
from backend.monitoring.execution_event import EventType
from backend.services.pipeline import ForgePipeline, PipelineStage
from backend.schemas.pm_schema import PMOutput


@pytest.fixture
def temp_store(tmp_path):
    """Fixture providing a fresh local artifact store and manager in tmp_path."""
    store = LocalJsonArtifactStore(storage_dir=str(tmp_path / "artifacts"))
    manager = ArtifactManager(store=store)
    return manager, tmp_path


def test_rollback_manager_creation(temp_store):
    """Test 1: RollbackManager initialization."""
    manager, _ = temp_store
    logger_inst = PipelineLogger()
    rollback_mgr = RollbackManager(artifact_manager=manager, pipeline_logger=logger_inst)
    assert rollback_mgr.artifact_manager == manager
    assert rollback_mgr.pipeline_logger == logger_inst


def test_retrieving_available_versions(temp_store):
    """Test 2: Retrieving all available artifact versions for a project and agent."""
    manager, _ = temp_store
    rollback_mgr = RollbackManager(artifact_manager=manager)

    art1 = manager.create_artifact("proj_v", "run_1", "pm", "PMOutput", {"project_name": "App V1"})
    art2 = manager.create_artifact("proj_v", "run_2", "pm", "PMOutput", {"project_name": "App V2"})
    art3 = manager.create_artifact("proj_v", "run_3", "pm", "PMOutput", {"project_name": "App V3"})

    versions = rollback_mgr.get_available_versions("proj_v", "pm")
    assert len(versions) == 3
    assert [v.version for v in versions] == [1, 2, 3]
    assert versions[0].artifact_id == art1.artifact_id
    assert versions[1].artifact_id == art2.artifact_id
    assert versions[2].artifact_id == art3.artifact_id


def test_valid_rollback_target(temp_store):
    """Test 3: Validating a valid rollback target."""
    manager, _ = temp_store
    rollback_mgr = RollbackManager(artifact_manager=manager)

    manager.create_artifact("proj_val", "run_1", "pm", "PMOutput", {"project_name": "V1"})
    validated = rollback_mgr.validate_rollback_target("proj_val", "pm", 1)
    assert validated.version == 1
    assert validated.content["project_name"] == "V1"


def test_invalid_artifact_id(temp_store):
    """Test 4: Target validation fails for invalid/non-existent artifact ID."""
    manager, _ = temp_store
    rollback_mgr = RollbackManager(artifact_manager=manager)

    with pytest.raises(RollbackValidationError) as exc_info:
        rollback_mgr.validate_rollback_target("proj_val", "pm", "art_non_existent")
    assert "not found" in str(exc_info.value)


def test_invalid_version(temp_store):
    """Test 5: Target validation fails for invalid version number."""
    manager, _ = temp_store
    rollback_mgr = RollbackManager(artifact_manager=manager)

    manager.create_artifact("proj_ver", "run_1", "pm", "PMOutput", {"project_name": "V1"})
    with pytest.raises(RollbackValidationError) as exc_info:
        rollback_mgr.validate_rollback_target("proj_ver", "pm", 99)
    assert "not found" in str(exc_info.value)


def test_failed_artifact_cannot_be_rollback_target(temp_store):
    """Test 6: FAILED artifacts cannot be selected as a rollback target."""
    manager, _ = temp_store
    rollback_mgr = RollbackManager(artifact_manager=manager)

    manager.create_artifact("proj_fail", "run_1", "pm", "PMOutput", {"project_name": "V1"})
    manager.create_artifact(
        "proj_fail", "run_2", "pm", "PMOutput", {"error": "PM Failed"}, status=ArtifactStatus.FAILED
    )

    with pytest.raises(RollbackValidationError) as exc_info:
        rollback_mgr.validate_rollback_target("proj_fail", "pm", 2)
    assert "Target must be COMPLETED" in str(exc_info.value)


def test_schema_invalid_artifact_cannot_be_rollback_target(temp_store):
    """Test 7: Schema-invalid artifacts cannot be selected as a rollback target."""
    manager, _ = temp_store
    rollback_mgr = RollbackManager(artifact_manager=manager)

    class StrictPMModel(BaseModel):
        project_name: str
        description: str

    # Create artifact missing required field 'description'
    manager.create_artifact("proj_schema", "run_1", "pm", "PMOutput", {"project_name": "V1"})

    with pytest.raises(RollbackValidationError) as exc_info:
        rollback_mgr.validate_rollback_target("proj_schema", "pm", 1, schema_cls=StrictPMModel)
    assert "validation failed" in str(exc_info.value)


def test_successful_rollback_additive(temp_store):
    """Test 8: Successful rollback is additive (creates a new version instead of deleting history)."""
    manager, _ = temp_store
    rollback_mgr = RollbackManager(artifact_manager=manager)

    v1 = manager.create_artifact("proj_add", "run_1", "pm", "PMOutput", {"project_name": "App Version 1"})
    v2 = manager.create_artifact("proj_add", "run_2", "pm", "PMOutput", {"project_name": "App Version 2"})
    v3 = manager.create_artifact("proj_add", "run_3", "pm", "PMOutput", {"project_name": "App Version 3"})

    result = rollback_mgr.rollback_to_version("proj_add", "pm", target_version=1, force=True)

    assert result.status == "COMPLETED"
    assert result.source_version == 3
    assert result.target_version == 1
    assert result.restored_version == 4

    # Fetch restored version 4
    v4 = manager.get_artifact(result.restored_artifact_id)
    assert v4.version == 4
    assert v4.content["project_name"] == "App Version 1"


def test_original_versions_remain_intact(temp_store):
    """Test 9: Historical artifact versions remain intact after rollback."""
    manager, _ = temp_store
    rollback_mgr = RollbackManager(artifact_manager=manager)

    manager.create_artifact("proj_intact", "run_1", "pm", "PMOutput", {"v": 1})
    manager.create_artifact("proj_intact", "run_2", "pm", "PMOutput", {"v": 2})
    manager.create_artifact("proj_intact", "run_3", "pm", "PMOutput", {"v": 3})

    rollback_mgr.rollback_to_version("proj_intact", "pm", target_version=1, force=True)

    versions = manager.get_all_versions("proj_intact", "pm")
    assert len(versions) == 4
    assert versions[0].content["v"] == 1
    assert versions[1].content["v"] == 2
    assert versions[2].content["v"] == 3
    assert versions[3].content["v"] == 1


def test_rollback_recovery_state_recorded(temp_store):
    """Test 10: Recovery state and metadata are properly recorded on the restored artifact."""
    manager, _ = temp_store
    rollback_mgr = RollbackManager(artifact_manager=manager)

    v1 = manager.create_artifact("proj_rec", "run_1", "pm", "PMOutput", {"v": 1})
    v2 = manager.create_artifact("proj_rec", "run_2", "pm", "PMOutput", {"v": 2})

    result = rollback_mgr.rollback_to_version(
        "proj_rec", "pm", target_version=1, reason="Reverting bug in v2", force=True
    )

    restored = manager.get_artifact(result.restored_artifact_id)
    assert restored.metadata["is_rollback"] is True
    assert restored.metadata["restored_from_version"] == 1
    assert restored.metadata["restored_from_artifact_id"] == v1.artifact_id
    assert restored.metadata["source_version"] == 2
    assert restored.metadata["source_artifact_id"] == v2.artifact_id
    assert restored.metadata["reason"] == "Reverting bug in v2"


def test_rollback_lineage_preserved(temp_store):
    """Test 11: Lineage is preserved across source and target artifacts in input_artifacts."""
    manager, _ = temp_store
    rollback_mgr = RollbackManager(artifact_manager=manager)

    v1 = manager.create_artifact("proj_lineage", "run_1", "pm", "PMOutput", {"v": 1})
    v2 = manager.create_artifact("proj_lineage", "run_2", "pm", "PMOutput", {"v": 2})

    result = rollback_mgr.rollback_to_version("proj_lineage", "pm", target_version=1, force=True)
    restored = manager.get_artifact(result.restored_artifact_id)

    assert v2.artifact_id in restored.input_artifacts
    assert v1.artifact_id in restored.input_artifacts


def test_rollback_monitoring_events_generated(temp_store):
    """Test 12: ROLLBACK_STARTED and ROLLBACK_COMPLETED monitoring events are logged."""
    manager, tmp_path = temp_store
    log_dir = tmp_path / "logs"
    logger_inst = PipelineLogger(log_dir=str(log_dir))
    rollback_mgr = RollbackManager(artifact_manager=manager, pipeline_logger=logger_inst)

    manager.create_artifact("proj_mon", "run_1", "pm", "PMOutput", {"v": 1})
    manager.create_artifact("proj_mon", "run_2", "pm", "PMOutput", {"v": 2})

    rollback_mgr.rollback_to_version("proj_mon", "pm", target_version=1, force=True)

    events = logger_inst.read_logs_from_file()
    event_types = [e.event_type for e in events]
    assert EventType.ROLLBACK_STARTED in event_types
    assert EventType.ROLLBACK_COMPLETED in event_types

    completed_evt = [e for e in events if e.event_type == EventType.ROLLBACK_COMPLETED][0]
    assert completed_evt.agent_name == "pm"
    assert completed_evt.duration_ms is not None


def test_rollback_failure_generates_event(temp_store):
    """Test 13: Rollback failures generate ROLLBACK_FAILED monitoring event."""
    manager, tmp_path = temp_store
    logger_inst = PipelineLogger(log_dir=str(tmp_path / "logs"))
    rollback_mgr = RollbackManager(artifact_manager=manager, pipeline_logger=logger_inst)

    manager.create_artifact("proj_fail_mon", "run_1", "pm", "PMOutput", {"v": 1})

    with pytest.raises(RollbackValidationError):
        rollback_mgr.rollback_to_version("proj_fail_mon", "pm", target_version=99)

    events = logger_inst.read_logs_from_file()
    event_types = [e.event_type for e in events]
    assert EventType.ROLLBACK_FAILED in event_types
    fail_evt = [e for e in events if e.event_type == EventType.ROLLBACK_FAILED][0]
    assert fail_evt.status == "FAILED"


def test_rollback_errors_sanitized(temp_store):
    """Test 14: Sensitive secrets in rollback reasons and error messages are sanitized."""
    manager, tmp_path = temp_store
    logger_inst = PipelineLogger(log_dir=str(tmp_path / "logs"))
    rollback_mgr = RollbackManager(artifact_manager=manager, pipeline_logger=logger_inst)

    v1 = manager.create_artifact("proj_secret", "run_1", "pm", "PMOutput", {"v": 1})
    v2 = manager.create_artifact("proj_secret", "run_2", "pm", "PMOutput", {"v": 2})

    secret_key = "AIzaSy1234567890123456789012345678901"
    reason_with_secret = f"Rolling back due to key={secret_key} password: mysecretpass123"

    result = rollback_mgr.rollback_to_version(
        "proj_secret", "pm", target_version=1, reason=reason_with_secret, force=True
    )

    assert secret_key not in result.reason
    assert "[REDACTED_GEMINI_KEY]" in result.reason
    assert "mysecretpass123" not in result.reason
    assert "password=[REDACTED]" in result.reason


def test_dependent_artifact_conflict_detected(temp_store):
    """Test 15: Dependency conflict is detected when rolling back upstream artifacts."""
    manager, _ = temp_store
    rollback_mgr = RollbackManager(artifact_manager=manager)

    manager.create_artifact("proj_dep", "run_1", "pm", "PMOutput", {"v": 1})
    manager.create_artifact("proj_dep", "run_2", "pm", "PMOutput", {"v": 2})
    manager.create_artifact("proj_dep", "run_2", "ui", "UIOutput", {"pages": []})

    # PM has active downstream dependent UI -> rollback should raise RollbackDependencyError
    with pytest.raises(RollbackDependencyError) as exc_info:
        rollback_mgr.rollback_to_version("proj_dep", "pm", target_version=1, force=False)

    assert "active downstream dependent artifacts exist for [ui]" in str(exc_info.value)

    # Overriding with force=True permits the rollback
    res = rollback_mgr.rollback_to_version("proj_dep", "pm", target_version=1, force=True)
    assert res.status == "COMPLETED"


def test_pipeline_rollback_stage_integration(tmp_path):
    """Test 16: ForgePipeline rollback_stage API integrates cleanly without breaking existing behavior."""
    pm_src = Path("outputs/pm_output.json")
    if pm_src.exists():
        (tmp_path / "pm_output.json").write_text(pm_src.read_text(encoding="utf-8"), encoding="utf-8")

    pipeline = ForgePipeline(
        user_prompt="Pipeline rollback test",
        project_id="proj_pipe_rb",
        run_id="run_pipe_rb",
        output_dir=str(tmp_path),
    )

    # Run PM stage twice by registering a handler that modifies output
    pipeline.run_stage(PipelineStage.PM)
    art1_id = pipeline.state.artifact_ids["pm"]

    def v2_handler(ctx):
        return {
            "project_name": "TaskFlow V2",
            "description": "Updated description",
            "features": ["Auth", "Dashboard"],
            "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
            "database_entities": [],
        }

    pipeline.register_agent_handler(PipelineStage.PM, v2_handler)
    pipeline.run_stage(PipelineStage.PM)
    art2_id = pipeline.state.artifact_ids["pm"]
    assert art1_id != art2_id

    # Roll back PM stage to version 1
    rb_res = pipeline.rollback_stage(PipelineStage.PM, target_version=1, force=True)
    assert rb_res.status == "COMPLETED"
    assert rb_res.restored_version == 3

    # Pipeline state updated to restored version 3
    assert pipeline.state.artifact_ids["pm"] == rb_res.restored_artifact_id
    assert pipeline.state.agent_outputs["pm"]["project_name"] == "TaskFlow"

    # Status summary remains 100% valid
    summary = pipeline.get_status_summary()
    assert summary["project_id"] == "proj_pipe_rb"
    assert summary["artifact_count"] >= 1
    assert len(pipeline.artifact_manager.get_all_versions(pipeline.state.project_id, "pm")) == 3
