"""Phase 3 Tests for Artifact Context Layer, Schema Validation, Lineage, and Agent Inter-Communication."""

import pytest
import json
from pathlib import Path
from pydantic import ValidationError

from backend.artifacts.artifact_schema import Artifact, ArtifactStatus
from backend.artifacts.artifact_store import LocalJsonArtifactStore
from backend.artifacts.artifact_manager import ArtifactManager, ArtifactValidationError
from backend.artifacts.artifact_context import ArtifactContext, ArtifactNotFoundError
from backend.services.pipeline import ForgePipeline, AgentStatus, PipelineStage, STAGE_ORDER
from backend.schemas.pm_schema import PMOutput
from backend.schemas.ui_schema import UIOutput
from backend.schemas.backend_schema import BackendOutput
from backend.schemas.db_schema import DBOutput
from backend.schemas.auth_schema import AuthOutput
from backend.schemas.qa_schema import QAOutput
from backend.schemas.deploy_schema import DeployOutput
from backend.agents.ui_agent import UIAgent
from backend.agents.backend_agent import BackendAgent
from backend.agents.db_agent import DBAgent
from backend.agents.auth_agent import AuthAgent
from backend.agents.qa_agent import QAAgent
from backend.agents.deploy_agent import DeployAgent


@pytest.fixture
def temp_artifact_manager(tmp_path):
    """Fixture providing a fresh ArtifactManager backed by a temporary directory."""
    store = LocalJsonArtifactStore(storage_dir=str(tmp_path / "artifacts"))
    return ArtifactManager(store=store)


def test_a_artifact_context_retrieves_pm_artifact(tmp_path, temp_artifact_manager):
    """Test A: Artifact context can retrieve PM artifact."""
    project_id = "proj_test_a"
    run_id = "run_test_a"

    pipeline = ForgePipeline(
        user_prompt="Task Tracker",
        project_id=project_id,
        run_id=run_id,
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pm_out = pipeline.run_stage(PipelineStage.PM)
    pm_art_id = pipeline.state.artifact_ids["pm"]

    ctx = ArtifactContext(
        artifact_manager=temp_artifact_manager,
        project_id=project_id,
        run_id=run_id,
        current_agent="ui",
        input_artifact_ids=[pm_art_id],
    )

    retrieved_pm = ctx.get_validated_content("pm", PMOutput)
    assert retrieved_pm is not None
    assert retrieved_pm.project_name == pm_out.project_name
    assert retrieved_pm.description == pm_out.description


def test_b_ui_consumes_pm_artifact_via_context(tmp_path, temp_artifact_manager):
    """Test B: UI agent can consume PM artifact via ArtifactContext."""
    pipeline = ForgePipeline(
        user_prompt="Note taking app",
        project_id="proj_test_b",
        run_id="run_test_b",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pipeline.run_stage(PipelineStage.PM)
    ui_out = pipeline.run_stage(PipelineStage.UI)

    assert isinstance(ui_out, UIOutput)
    assert ui_out.project_name == "TaskFlow" or "Note" in ui_out.project_name or len(ui_out.pages) > 0

    ui_art = temp_artifact_manager.get_artifact(pipeline.state.artifact_ids["ui"])
    assert pipeline.state.artifact_ids["pm"] in ui_art.input_artifacts


def test_c_backend_consumes_pm_and_ui_artifacts(tmp_path, temp_artifact_manager):
    """Test C: Backend agent can consume PM + UI artifacts via ArtifactContext."""
    pipeline = ForgePipeline(
        user_prompt="E-commerce portal",
        project_id="proj_test_c",
        run_id="run_test_c",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pipeline.run_stage(PipelineStage.PM)
    pipeline.run_stage(PipelineStage.UI)
    backend_out = pipeline.run_stage(PipelineStage.BACKEND)

    assert isinstance(backend_out, BackendOutput)
    backend_art = temp_artifact_manager.get_artifact(pipeline.state.artifact_ids["backend"])
    assert pipeline.state.artifact_ids["pm"] in backend_art.input_artifacts
    assert pipeline.state.artifact_ids["ui"] in backend_art.input_artifacts


def test_d_db_consumes_pm_and_backend_artifacts(tmp_path, temp_artifact_manager):
    """Test D: DB agent can consume PM + Backend artifacts via ArtifactContext."""
    pipeline = ForgePipeline(
        user_prompt="Inventory management system",
        project_id="proj_test_d",
        run_id="run_test_d",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pipeline.run_stage(PipelineStage.PM)
    pipeline.run_stage(PipelineStage.UI)
    pipeline.run_stage(PipelineStage.BACKEND)
    db_out = pipeline.run_stage(PipelineStage.DB)

    assert isinstance(db_out, DBOutput)
    db_art = temp_artifact_manager.get_artifact(pipeline.state.artifact_ids["db"])
    assert pipeline.state.artifact_ids["pm"] in db_art.input_artifacts
    assert pipeline.state.artifact_ids["backend"] in db_art.input_artifacts


def test_e_auth_consumes_pm_backend_and_db_artifacts(tmp_path, temp_artifact_manager):
    """Test E: Auth agent can consume PM + Backend + DB artifacts via ArtifactContext."""
    pipeline = ForgePipeline(
        user_prompt="Banking portal",
        project_id="proj_test_e",
        run_id="run_test_e",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pipeline.run_stage(PipelineStage.PM)
    pipeline.run_stage(PipelineStage.UI)
    pipeline.run_stage(PipelineStage.BACKEND)
    pipeline.run_stage(PipelineStage.DB)
    auth_out = pipeline.run_stage(PipelineStage.AUTH)

    assert isinstance(auth_out, AuthOutput)
    auth_art = temp_artifact_manager.get_artifact(pipeline.state.artifact_ids["auth"])
    assert pipeline.state.artifact_ids["pm"] in auth_art.input_artifacts
    assert pipeline.state.artifact_ids["backend"] in auth_art.input_artifacts
    assert pipeline.state.artifact_ids["db"] in auth_art.input_artifacts


def test_f_qa_consumes_all_required_artifacts(tmp_path, temp_artifact_manager):
    """Test F: QA agent can consume PM + UI + Backend + DB + Auth artifacts via ArtifactContext."""
    pipeline = ForgePipeline(
        user_prompt="Healthcare app",
        project_id="proj_test_f",
        run_id="run_test_f",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pipeline.run_stage(PipelineStage.PM)
    pipeline.run_stage(PipelineStage.UI)
    pipeline.run_stage(PipelineStage.BACKEND)
    pipeline.run_stage(PipelineStage.DB)
    pipeline.run_stage(PipelineStage.AUTH)
    qa_out = pipeline.run_stage(PipelineStage.QA)

    assert isinstance(qa_out, QAOutput)
    qa_art = temp_artifact_manager.get_artifact(pipeline.state.artifact_ids["qa"])
    for req_stage in ["pm", "ui", "backend", "db", "auth"]:
        assert pipeline.state.artifact_ids[req_stage] in qa_art.input_artifacts


def test_g_deploy_consumes_all_required_artifacts(tmp_path, temp_artifact_manager):
    """Test G: Deploy agent can consume PM + UI + Backend + DB + Auth + QA artifacts via ArtifactContext."""
    pipeline = ForgePipeline(
        user_prompt="SaaS analytics platform",
        project_id="proj_test_g",
        run_id="run_test_g",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pipeline.run_pipeline()
    deploy_art = temp_artifact_manager.get_artifact(pipeline.state.artifact_ids["deploy"])

    for req_stage in ["pm", "ui", "backend", "db", "auth", "qa"]:
        assert pipeline.state.artifact_ids[req_stage] in deploy_art.input_artifacts


def test_h_artifact_contents_are_schema_validated(tmp_path, temp_artifact_manager):
    """Test H: Artifact contents are validated against Pydantic schema."""
    project_id = "proj_test_h"
    run_id = "run_test_h"

    temp_artifact_manager.create_artifact(
        project_id=project_id,
        run_id=run_id,
        agent_name="pm",
        artifact_type="PMOutput",
        content={
            "project_name": "Valid Project",
            "description": "Valid Description",
            "features": ["f1"],
            "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
            "database_entities": [],
        },
        schema_cls=PMOutput,
    )

    ctx = ArtifactContext(
        artifact_manager=temp_artifact_manager,
        project_id=project_id,
        run_id=run_id,
    )

    validated_pm = ctx.get_validated_content("pm", PMOutput)
    assert isinstance(validated_pm, PMOutput)
    assert validated_pm.project_name == "Valid Project"


def test_i_missing_artifact_causes_controlled_failure(tmp_path, temp_artifact_manager):
    """Test I: Missing required artifact causes controlled ArtifactNotFoundError."""
    ctx = ArtifactContext(
        artifact_manager=temp_artifact_manager,
        project_id="nonexistent_proj",
        run_id="nonexistent_run",
    )

    with pytest.raises(ArtifactNotFoundError):
        ctx.get_validated_content("pm", PMOutput, optional=False)


def test_j_invalid_artifact_causes_controlled_failure(tmp_path, temp_artifact_manager):
    """Test J: Invalid artifact payload content causes controlled ArtifactValidationError."""
    project_id = "proj_test_j"
    run_id = "run_test_j"

    # Create artifact with invalid content (missing required fields for PMOutput)
    temp_artifact_manager.create_artifact(
        project_id=project_id,
        run_id=run_id,
        agent_name="pm",
        artifact_type="PMOutput",
        content={"project_name": "Incomplete PM"},  # Missing description, features, etc.
    )

    ctx = ArtifactContext(
        artifact_manager=temp_artifact_manager,
        project_id=project_id,
        run_id=run_id,
    )

    with pytest.raises(ArtifactValidationError):
        ctx.get_validated_content("pm", PMOutput)


def test_k_correct_artifact_lineage_is_preserved(tmp_path, temp_artifact_manager):
    """Test K: Correct artifact lineage is preserved across all 7 stages."""
    pipeline = ForgePipeline(
        user_prompt="Full lineage verification app",
        project_id="proj_lineage_001",
        run_id="run_lineage_001",
        output_dir=str(tmp_path),
        artifact_manager=temp_artifact_manager,
    )

    pipeline.run_pipeline()
    ids = pipeline.state.artifact_ids

    pm_art = temp_artifact_manager.get_artifact(ids["pm"])
    assert pm_art.input_artifacts == []

    ui_art = temp_artifact_manager.get_artifact(ids["ui"])
    assert ui_art.input_artifacts == [ids["pm"]]

    backend_art = temp_artifact_manager.get_artifact(ids["backend"])
    assert backend_art.input_artifacts == [ids["pm"], ids["ui"]]

    db_art = temp_artifact_manager.get_artifact(ids["db"])
    assert db_art.input_artifacts == [ids["pm"], ids["backend"]]

    auth_art = temp_artifact_manager.get_artifact(ids["auth"])
    assert auth_art.input_artifacts == [ids["pm"], ids["backend"], ids["db"]]

    qa_art = temp_artifact_manager.get_artifact(ids["qa"])
    assert qa_art.input_artifacts == [ids["pm"], ids["ui"], ids["backend"], ids["db"], ids["auth"]]

    deploy_art = temp_artifact_manager.get_artifact(ids["deploy"])
    assert deploy_art.input_artifacts == [ids["pm"], ids["ui"], ids["backend"], ids["db"], ids["auth"], ids["qa"]]


def test_l_existing_pipeline_behavior_still_works(tmp_path):
    """Test L: Existing pipeline execution and JSON outputs still work seamlessly."""
    pipeline = ForgePipeline(
        user_prompt="Backward compatibility test app",
        output_dir=str(tmp_path),
    )

    state = pipeline.run_pipeline()
    assert state.execution_status == AgentStatus.COMPLETED

    for stage in STAGE_ORDER:
        file_path = tmp_path / f"{stage.value}_output.json"
        assert file_path.exists()
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert isinstance(data, dict)
