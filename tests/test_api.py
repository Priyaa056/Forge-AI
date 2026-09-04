"""API Unit & Integration Tests for Phase 6A Backend API Foundation."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app, ACTIVE_PIPELINES
from backend.services.pipeline import ForgePipeline, PipelineStage


@pytest.fixture
def api_client(tmp_path):
    """Fixture providing FastAPI TestClient and clearing active pipelines registry."""
    ACTIVE_PIPELINES.clear()
    pm_src = Path("outputs/pm_output.json")
    if pm_src.exists():
        (tmp_path / "pm_output.json").write_text(pm_src.read_text(encoding="utf-8"), encoding="utf-8")
    return TestClient(app), tmp_path


def test_read_root_and_health(api_client):
    """Test GET / and GET /health endpoints."""
    client, _ = api_client
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert res_root.json()["status"] == "online"

    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"


def test_create_project_run_api(api_client):
    """Test POST /api/projects creating and executing a new pipeline run."""
    client, tmp_dir = api_client

    payload = {
        "user_prompt": "Build TaskFlow app for Phase 6A test",
        "project_id": "proj_api_create",
        "output_dir": str(tmp_dir),
        "run_immediately": True,
    }

    res = client.post("/api/projects", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["project_id"] == "proj_api_create"
    assert "run_id" in data
    assert data["execution_status"] == "COMPLETED"
    assert data["successful_agent_count"] == 7


def test_get_run_status_api(api_client):
    """Test GET /api/projects/{project_id}/runs/{run_id} for active and non-existent runs."""
    client, tmp_dir = api_client

    create_res = client.post(
        "/api/projects",
        json={
            "user_prompt": "Get run status app",
            "project_id": "proj_status_api",
            "output_dir": str(tmp_dir),
            "run_immediately": True,
        },
    )
    run_id = create_res.json()["run_id"]

    res_status = client.get(f"/api/projects/proj_status_api/runs/{run_id}")
    assert res_status.status_code == 200
    assert res_status.json()["run_id"] == run_id

    # Non-existent run
    res_404 = client.get("/api/projects/proj_status_api/runs/run_non_existent")
    assert res_404.status_code == 404


def test_get_run_artifacts_api(api_client):
    """Test GET /api/projects/{project_id}/runs/{run_id}/artifacts."""
    client, tmp_dir = api_client

    create_res = client.post(
        "/api/projects",
        json={
            "user_prompt": "Artifacts list app",
            "project_id": "proj_arts_api",
            "output_dir": str(tmp_dir),
            "run_immediately": True,
        },
    )
    run_id = create_res.json()["run_id"]

    res = client.get(f"/api/projects/proj_arts_api/runs/{run_id}/artifacts")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 7
    assert len(data["artifacts"]) == 7


def test_get_artifact_by_id_api(api_client):
    """Test GET /api/artifacts/{artifact_id} for valid and invalid artifact IDs."""
    client, tmp_dir = api_client

    create_res = client.post(
        "/api/projects",
        json={
            "user_prompt": "Single artifact app",
            "project_id": "proj_single_art",
            "output_dir": str(tmp_dir),
            "run_immediately": True,
        },
    )
    run_id = create_res.json()["run_id"]
    pm_art_id = create_res.json()["artifact_ids"]["pm"]

    res_art = client.get(f"/api/artifacts/{pm_art_id}")
    assert res_art.status_code == 200
    assert res_art.json()["artifact_id"] == pm_art_id
    assert res_art.json()["agent_name"] == "pm"

    # Non-existent artifact ID
    res_404 = client.get("/api/artifacts/art_non_existent_123")
    assert res_404.status_code == 404


def test_get_run_events_api(api_client):
    """Test GET /api/projects/{project_id}/runs/{run_id}/events."""
    client, tmp_dir = api_client

    create_res = client.post(
        "/api/projects",
        json={
            "user_prompt": "Events list app",
            "project_id": "proj_events_api",
            "output_dir": str(tmp_dir),
            "run_immediately": True,
        },
    )
    run_id = create_res.json()["run_id"]

    res_evts = client.get(f"/api/projects/proj_events_api/runs/{run_id}/events")
    assert res_evts.status_code == 200
    data = res_evts.json()
    assert data["count"] >= 23
    assert len(data["events"]) >= 23


def test_rollback_stage_api(api_client):
    """Test POST /api/projects/{project_id}/runs/{run_id}/rollback."""
    client, tmp_dir = api_client

    pipeline = ForgePipeline(
        user_prompt="Rollback API app",
        project_id="proj_rb_api",
        run_id="run_rb_api",
        output_dir=str(tmp_dir),
    )
    pipeline.run_stage(PipelineStage.PM)

    # Register modified handler for PM stage run 2
    def pm_v2_handler(ctx):
        return {
            "project_name": "TaskFlow V2",
            "description": "Updated",
            "features": ["Auth"],
            "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
            "database_entities": [],
        }

    pipeline.register_agent_handler(PipelineStage.PM, pm_v2_handler)
    pipeline.run_stage(PipelineStage.PM)
    ACTIVE_PIPELINES["proj_rb_api:run_rb_api"] = pipeline

    # Roll back PM stage to version 1 with force=True
    rollback_payload = {
        "agent_name": "pm",
        "target_version": 1,
        "reason": "Reverting to version 1",
        "force": True,
    }

    res_rb = client.post("/api/projects/proj_rb_api/runs/run_rb_api/rollback", json=rollback_payload)
    assert res_rb.status_code == 200
    data = res_rb.json()
    assert data["status"] == "COMPLETED"
    assert data["target_version"] == 1
    assert data["restored_version"] == 3


def test_rollback_validation_error_api(api_client):
    """Test POST /api/projects/{project_id}/runs/{run_id}/rollback returning 400 Bad Request on invalid version."""
    client, tmp_dir = api_client

    pipeline = ForgePipeline(
        user_prompt="Rollback validation error app",
        project_id="proj_rb_val_err",
        run_id="run_rb_val_err",
        output_dir=str(tmp_dir),
    )
    pipeline.run_stage(PipelineStage.PM)
    ACTIVE_PIPELINES["proj_rb_val_err:run_rb_val_err"] = pipeline

    # Target version 99 does not exist -> 400 Bad Request
    rollback_payload = {
        "agent_name": "pm",
        "target_version": 99,
        "force": True,
    }

    res = client.post("/api/projects/proj_rb_val_err/runs/run_rb_val_err/rollback", json=rollback_payload)
    assert res.status_code == 400
    assert "not found" in res.json()["detail"]


def test_rollback_dependency_error_api(api_client):
    """Test POST /api/projects/{project_id}/runs/{run_id}/rollback returning 409 Conflict on dependency conflict."""
    client, tmp_dir = api_client

    pipeline = ForgePipeline(
        user_prompt="Rollback dependency error app",
        project_id="proj_rb_dep_err",
        run_id="run_rb_dep_err",
        output_dir=str(tmp_dir),
    )
    pipeline.run_stage(PipelineStage.PM)
    pipeline.run_stage(PipelineStage.PM)
    pipeline.run_stage(PipelineStage.UI)  # UI depends on PM
    ACTIVE_PIPELINES["proj_rb_dep_err:run_rb_dep_err"] = pipeline

    # Rolling back PM without force=True raises 409 Conflict due to active UI artifact
    rollback_payload = {
        "agent_name": "pm",
        "target_version": 1,
        "force": False,
    }

    res = client.post("/api/projects/proj_rb_dep_err/runs/run_rb_dep_err/rollback", json=rollback_payload)
    assert res.status_code == 409
    assert "active downstream dependent artifacts exist for [ui]" in res.json()["detail"]
