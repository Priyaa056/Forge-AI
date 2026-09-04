"""Tests for FORGE AI Orchestration Pipeline and Artifact Manager integration."""

import pytest
import json
from pathlib import Path
from pydantic import ValidationError

from backend.artifacts.artifact_schema import ArtifactStatus
from backend.artifacts.artifact_store import LocalJsonArtifactStore
from backend.artifacts.artifact_manager import ArtifactManager
from backend.services.pipeline import (
    ForgePipeline,
    AgentStatus,
    PipelineStage,
    STAGE_ORDER,
)
from backend.schemas.pm_schema import PMOutput
from backend.schemas.ui_schema import UIOutput


@pytest.fixture
def temp_artifact_manager(tmp_path):
    """Provides a fresh ArtifactManager backed by a temp directory."""
    store = LocalJsonArtifactStore(storage_dir=str(tmp_path / "artifacts"))
    return ArtifactManager(store=store)


def test_pipeline_initialization_with_artifact_manager(tmp_path, temp_artifact_manager):
    """TEST 1: Pipeline can initialize with ArtifactManager and custom project/run IDs."""
    pipeline = ForgePipeline(
        user_prompt="Build a task manager",
        project_id="proj_test_001",
        run_id="run_test_001",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    assert pipeline.artifact_manager is temp_artifact_manager
    assert pipeline.state.project_id == "proj_test_001"
    assert pipeline.state.run_id == "run_test_001"
    assert pipeline.state.execution_status == AgentStatus.PENDING


def test_pm_execution_creates_pm_artifact(tmp_path, temp_artifact_manager):
    """TEST 2: Successful PM execution creates a PM artifact in ArtifactManager."""
    pipeline = ForgePipeline(
        user_prompt="Build a blog platform",
        project_id="proj_blog_001",
        run_id="run_blog_001",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pm_out = pipeline.run_stage(PipelineStage.PM)
    assert isinstance(pm_out, PMOutput)

    pm_artifact_id = pipeline.state.artifact_ids.get("pm")
    assert pm_artifact_id is not None

    artifact = temp_artifact_manager.get_artifact(pm_artifact_id)
    assert artifact is not None
    assert artifact.status == ArtifactStatus.COMPLETED


def test_artifact_contains_correct_project_id(tmp_path, temp_artifact_manager):
    """TEST 3: Artifact contains correct project_id."""
    project_id = "proj_unique_123"
    pipeline = ForgePipeline(
        user_prompt="E-commerce store",
        project_id=project_id,
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pipeline.run_stage(PipelineStage.PM)
    pm_artifact_id = pipeline.state.artifact_ids["pm"]
    artifact = temp_artifact_manager.get_artifact(pm_artifact_id)

    assert artifact.project_id == project_id


def test_artifact_contains_correct_run_id(tmp_path, temp_artifact_manager):
    """TEST 4: Artifact contains correct run_id."""
    run_id = "run_unique_456"
    pipeline = ForgePipeline(
        user_prompt="Social media app",
        run_id=run_id,
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pipeline.run_stage(PipelineStage.PM)
    pm_artifact_id = pipeline.state.artifact_ids["pm"]
    artifact = temp_artifact_manager.get_artifact(pm_artifact_id)

    assert artifact.run_id == run_id


def test_artifact_contains_correct_agent_name(tmp_path, temp_artifact_manager):
    """TEST 5: Artifact contains correct agent_name."""
    pipeline = ForgePipeline(
        user_prompt="CRM System",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pipeline.run_stage(PipelineStage.PM)
    pm_art = temp_artifact_manager.get_artifact(pipeline.state.artifact_ids["pm"])
    assert pm_art.agent_name == "pm"

    pipeline.run_stage(PipelineStage.UI)
    ui_art = temp_artifact_manager.get_artifact(pipeline.state.artifact_ids["ui"])
    assert ui_art.agent_name == "ui"


def test_artifact_contains_correct_artifact_type(tmp_path, temp_artifact_manager):
    """TEST 6: Artifact contains correct artifact_type descriptor."""
    pipeline = ForgePipeline(
        user_prompt="Analytics dashboard",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pipeline.run_stage(PipelineStage.PM)
    pm_art = temp_artifact_manager.get_artifact(pipeline.state.artifact_ids["pm"])
    assert pm_art.artifact_type == "PMOutput"

    pipeline.run_stage(PipelineStage.UI)
    ui_art = temp_artifact_manager.get_artifact(pipeline.state.artifact_ids["ui"])
    assert ui_art.artifact_type == "UIOutput"


def test_artifact_content_matches_agent_output(tmp_path, temp_artifact_manager):
    """TEST 7: Artifact content matches the structured agent output payload."""
    pipeline = ForgePipeline(
        user_prompt="Fitness tracker",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pm_out = pipeline.run_stage(PipelineStage.PM)
    pm_art = temp_artifact_manager.get_artifact(pipeline.state.artifact_ids["pm"])

    assert pm_art.content["project_name"] == pm_out.project_name
    assert pm_art.content["description"] == pm_out.description
    assert pm_art.content["features"] == pm_out.features


def test_ui_artifact_records_pm_lineage(tmp_path, temp_artifact_manager):
    """TEST 8: UI artifact records PM artifact ID in input_artifacts lineage."""
    pipeline = ForgePipeline(
        user_prompt="Recipe sharing app",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pipeline.run_stage(PipelineStage.PM)
    pm_art_id = pipeline.state.artifact_ids["pm"]

    pipeline.run_stage(PipelineStage.UI)
    ui_art_id = pipeline.state.artifact_ids["ui"]
    ui_art = temp_artifact_manager.get_artifact(ui_art_id)

    assert pm_art_id in ui_art.input_artifacts


def test_downstream_artifacts_preserve_lineage(tmp_path, temp_artifact_manager):
    """TEST 9: Downstream artifacts preserve full lineage across all 7 stages."""
    pipeline = ForgePipeline(
        user_prompt="Portfolio Builder",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pipeline.run_pipeline()
    art_ids = pipeline.state.artifact_ids

    # UI lineage includes PM
    ui_art = temp_artifact_manager.get_artifact(art_ids["ui"])
    assert art_ids["pm"] in ui_art.input_artifacts

    # Backend lineage includes PM & UI
    backend_art = temp_artifact_manager.get_artifact(art_ids["backend"])
    assert art_ids["pm"] in backend_art.input_artifacts
    assert art_ids["ui"] in backend_art.input_artifacts

    # DB lineage includes PM & Backend
    db_art = temp_artifact_manager.get_artifact(art_ids["db"])
    assert art_ids["pm"] in db_art.input_artifacts
    assert art_ids["backend"] in db_art.input_artifacts

    # Auth lineage includes PM, Backend & DB
    auth_art = temp_artifact_manager.get_artifact(art_ids["auth"])
    assert art_ids["pm"] in auth_art.input_artifacts
    assert art_ids["backend"] in auth_art.input_artifacts
    assert art_ids["db"] in auth_art.input_artifacts

    # QA lineage includes PM, UI, Backend, DB & Auth
    qa_art = temp_artifact_manager.get_artifact(art_ids["qa"])
    assert art_ids["pm"] in qa_art.input_artifacts
    assert art_ids["auth"] in qa_art.input_artifacts

    # Deploy lineage includes QA
    deploy_art = temp_artifact_manager.get_artifact(art_ids["deploy"])
    assert art_ids["qa"] in deploy_art.input_artifacts


def test_artifact_ids_stored_in_pipeline_state(tmp_path, temp_artifact_manager):
    """TEST 10: Artifact IDs are tracked in pipeline state and get_status_summary()."""
    pipeline = ForgePipeline(
        user_prompt="Workflow automation tool",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pipeline.run_stage(PipelineStage.PM)
    pipeline.run_stage(PipelineStage.UI)

    summary = pipeline.get_status_summary()
    assert "artifact_ids" in summary
    assert "pm" in summary["artifact_ids"]
    assert "ui" in summary["artifact_ids"]
    assert summary["artifact_ids"]["pm"] == pipeline.state.artifact_ids["pm"]


def test_failed_agent_execution_creates_failed_artifact(tmp_path, temp_artifact_manager):
    """TEST 11: Failed agent execution creates FAILED artifact in ArtifactManager."""
    pipeline = ForgePipeline(
        user_prompt="Broken Agent Test App",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    def failing_backend_handler(ctx):
        raise RuntimeError("Database connection timed out in backend agent")

    pipeline.register_agent_handler(PipelineStage.BACKEND, failing_backend_handler)

    pipeline.run_stage(PipelineStage.PM)
    with pytest.raises(RuntimeError):
        pipeline.run_stage(PipelineStage.BACKEND)

    assert pipeline.state.agent_statuses[PipelineStage.BACKEND] == AgentStatus.FAILED
    assert "backend" in pipeline.state.artifact_ids

    failed_art_id = pipeline.state.artifact_ids["backend"]
    failed_art = temp_artifact_manager.get_artifact(failed_art_id)

    assert failed_art is not None
    assert failed_art.status == ArtifactStatus.FAILED
    assert failed_art.agent_name == "backend"
    assert "Database connection timed out" in failed_art.content["error"]


def test_existing_pipeline_behavior_remains_intact(tmp_path):
    """TEST 12: Existing pipeline behavior remains intact (uses default ArtifactManager)."""
    pipeline = ForgePipeline(
        user_prompt="Standard test app",
        output_dir=str(tmp_path),
    )

    state = pipeline.run_pipeline()
    assert state.execution_status == AgentStatus.COMPLETED

    summary = pipeline.get_status_summary()
    assert summary["execution_status"] == AgentStatus.COMPLETED
    assert len(summary["completed_stages"]) == 7

    for stage in STAGE_ORDER:
        stage_file = tmp_path / f"{stage.value}_output.json"
        assert stage_file.exists()
