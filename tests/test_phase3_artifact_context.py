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




