"""Unit tests for FORGE AI Artifact Management (Schema, Store, Manager, Versioning, Lineage, Security)."""

import pytest
from backend.artifacts import (
    Artifact,
    ArtifactStatus,
    LocalJsonArtifactStore,
    ArtifactManager,
    ArtifactSecurityError,
    ArtifactValidationError,
)
from backend.schemas.pm_schema import PMOutput
from backend.schemas.ui_schema import UIOutput
from backend.schemas.backend_schema import BackendOutput, EndpointSpec, ResponseSchemaSpec


@pytest.fixture
def temp_store(tmp_path):
    """Provides an isolated LocalJsonArtifactStore instance in temporary directory."""
    return LocalJsonArtifactStore(storage_dir=str(tmp_path / "artifacts"))


@pytest.fixture
def artifact_mgr(temp_store):
    """Provides an ArtifactManager instance with isolated temporary storage."""
    return ArtifactManager(store=temp_store)


def test_1_artifact_creation(artifact_mgr):
    """Test 1: Verify artifact creation with valid parameters and defaults."""
    pm_content = PMOutput(
        project_name="TestApp",
        description="A test application",
        features=["Auth", "Dashboard"],
        tech_stack={"frontend": "React", "backend": "FastAPI"},
        database_entities=[]
    )

    artifact = artifact_mgr.create_artifact(
        project_id="proj_101",
        run_id="run_001",
        agent_name="pm",
        artifact_type="PMOutput",
        content=pm_content,
        metadata={"author": "PM Agent"}
    )

    assert isinstance(artifact, Artifact)
    assert artifact.project_id == "proj_101"
    assert artifact.run_id == "run_001"
    assert artifact.agent_name == "pm"
    assert artifact.artifact_type == "PMOutput"
    assert artifact.version == 1
    assert artifact.status == ArtifactStatus.COMPLETED
    assert artifact.content["project_name"] == "TestApp"
    assert artifact.metadata["author"] == "PM Agent"
    assert isinstance(artifact.artifact_id, str)
    assert len(artifact.artifact_id) > 0


def test_2_artifact_validation(artifact_mgr):
    """Test 2: Verify artifact validation against schema and structure."""
    pm_content = PMOutput(
        project_name="ValidApp",
        description="Valid description",
        features=["Feature 1"],
        tech_stack={},
        database_entities=[]
    )

    artifact = artifact_mgr.create_artifact(
        project_id="proj_102",
        run_id="run_001",
        agent_name="pm",
        artifact_type="PMOutput",
        content=pm_content
    )

    # Validate valid artifact with schema class
    assert artifact_mgr.validate_artifact(artifact, schema_cls=PMOutput) is True

    # Validate valid artifact without schema class
    assert artifact_mgr.validate_artifact(artifact) is True


def test_3_artifact_persistence(temp_store, tmp_path):
    """Test 3: Verify artifact persistence on disk in JSON format and reloadability."""
    manager1 = ArtifactManager(store=temp_store)

    art = manager1.create_artifact(
        project_id="proj_103",
        run_id="run_001",
        agent_name="pm",
        artifact_type="PMOutput",
        content={"project_name": "PersistentApp", "features": ["F1"]}
    )

    # Initialize a second manager pointing to the exact same store directory
    manager2 = ArtifactManager(store=LocalJsonArtifactStore(storage_dir=str(tmp_path / "artifacts")))
    retrieved = manager2.get_artifact(art.artifact_id)

    assert retrieved is not None
    assert retrieved.artifact_id == art.artifact_id
    assert retrieved.content["project_name"] == "PersistentApp"


def test_4_artifact_retrieval(artifact_mgr):
    """Test 4: Verify artifact retrieval by artifact_id."""
    art1 = artifact_mgr.create_artifact(
        project_id="proj_104",
        run_id="run_001",
        agent_name="pm",
        artifact_type="PMOutput",
        content={"project_name": "AppOne"}
    )

    art2 = artifact_mgr.create_artifact(
        project_id="proj_104",
        run_id="run_001",
        agent_name="ui",
        artifact_type="UIOutput",
        content={"project_name": "AppOne", "framework": "React"}
    )

    retrieved = artifact_mgr.get_artifact(art1.artifact_id)
    assert retrieved is not None
    assert retrieved.artifact_id == art1.artifact_id
    assert retrieved.agent_name == "pm"

    retrieved_ui = artifact_mgr.get_artifact(art2.artifact_id)
    assert retrieved_ui is not None
    assert retrieved_ui.artifact_id == art2.artifact_id
    assert retrieved_ui.agent_name == "ui"


def test_5_latest_artifact_retrieval(artifact_mgr):
    """Test 5: Verify get_latest_artifact returns the highest version created."""
    project_id = "proj_105"

    art_v1 = artifact_mgr.create_artifact(
        project_id=project_id,
        run_id="run_001",
        agent_name="pm",
        artifact_type="PMOutput",
        content={"project_name": "VersionedApp", "version_note": "v1"}
    )

    art_v2 = artifact_mgr.create_artifact(
        project_id=project_id,
        run_id="run_002",
        agent_name="pm",
        artifact_type="PMOutput",
        content={"project_name": "VersionedApp", "version_note": "v2"}
    )

    latest = artifact_mgr.get_latest_artifact(project_id=project_id, agent_name="pm")
    assert latest is not None
    assert latest.version == 2
    assert latest.artifact_id == art_v2.artifact_id
    assert latest.content["version_note"] == "v2"


def test_6_artifact_versioning(artifact_mgr):
    """Test 6: Verify versioning does not overwrite version 1 when creating version 2."""
    project_id = "proj_106"

    v1 = artifact_mgr.create_artifact(
        project_id=project_id,
        run_id="run_001",
        agent_name="pm",
        artifact_type="PMOutput",
        content={"project_name": "SpecV1"}
    )
    assert v1.version == 1

    v2 = artifact_mgr.create_artifact(
        project_id=project_id,
        run_id="run_002",
        agent_name="pm",
        artifact_type="PMOutput",
        content={"project_name": "SpecV2"}
    )
    assert v2.version == 2

    # Verify both versions exist and can be retrieved independently
    retrieved_v1 = artifact_mgr.get_artifact_version(project_id, "pm", version=1)
    retrieved_v2 = artifact_mgr.get_artifact_version(project_id, "pm", version=2)

    assert retrieved_v1 is not None
    assert retrieved_v1.content["project_name"] == "SpecV1"
    assert retrieved_v2 is not None
    assert retrieved_v2.content["project_name"] == "SpecV2"

    all_versions = artifact_mgr.get_all_versions(project_id, "pm")
    assert len(all_versions) == 2
    assert [v.version for v in all_versions] == [1, 2]


def test_7_artifact_lineage(artifact_mgr):
    """Test 7: Verify input_artifacts lineage tracking across multi-agent chain."""
    project_id = "proj_107"
    run_id = "run_001"

    # Step 1: PM Artifact
    pm_art = artifact_mgr.create_artifact(
        project_id=project_id,
        run_id=run_id,
        agent_name="pm",
        artifact_type="PMOutput",
        content={"project_name": "LineageApp"}
    )

    # Step 2: UI Artifact consumes PM Artifact V1
    ui_art = artifact_mgr.create_artifact(
        project_id=project_id,
        run_id=run_id,
        agent_name="ui",
        artifact_type="UIOutput",
        content={"project_name": "LineageApp", "framework": "React"},
        input_artifacts=[pm_art.artifact_id]
    )

    # Step 3: Backend Artifact consumes PM Artifact V1 & UI Artifact V1
    backend_art = artifact_mgr.create_artifact(
        project_id=project_id,
        run_id=run_id,
        agent_name="backend",
        artifact_type="BackendOutput",
        content={"project_name": "LineageApp", "architecture": "FastAPI"},
        input_artifacts=[pm_art.artifact_id, ui_art.artifact_id]
    )

    assert ui_art.input_artifacts == [pm_art.artifact_id]
    assert backend_art.input_artifacts == [pm_art.artifact_id, ui_art.artifact_id]


def test_8_invalid_artifact_handling(artifact_mgr):
    """Test 8: Verify secret scanning rejection and schema validation error handling."""
    project_id = "proj_108"

    # 8a: Secret scanning rejection for API Key in content
    with pytest.raises(ArtifactSecurityError):
        artifact_mgr.create_artifact(
            project_id=project_id,
            run_id="run_001",
            agent_name="backend",
            artifact_type="BackendOutput",
            content={"api_key": "sk-1234567890abcdef1234567890"}
        )

    # 8b: Secret scanning rejection for JWT secret in metadata
    with pytest.raises(ArtifactSecurityError):
        artifact_mgr.create_artifact(
            project_id=project_id,
            run_id="run_001",
            agent_name="auth",
            artifact_type="AuthOutput",
            content={"status": "ok"},
            metadata={"jwt_secret": "my-secret-key-phrase"}
        )

    # 8c: Schema validation failure when invalid schema content provided
    with pytest.raises(ArtifactValidationError):
        artifact_mgr.create_artifact(
            project_id=project_id,
            run_id="run_001",
            agent_name="pm",
            artifact_type="PMOutput",
            content={"bad_field": 123},  # Missing required fields project_name, etc.
            schema_cls=PMOutput
        )
