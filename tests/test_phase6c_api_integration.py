"""Phase 6C FORGE AI End-to-End API Integration Testing Suite."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app, ACTIVE_PIPELINES
from backend.services.pipeline import ForgePipeline, PipelineStage, AgentStatus


@pytest.fixture
def api_client_p6c(tmp_path):
    """Fixture providing FastAPI TestClient and clearing active pipelines registry with isolated workspace."""
    ACTIVE_PIPELINES.clear()
    pm_src = Path("outputs/pm_output.json")
    if pm_src.exists():
        (tmp_path / "pm_output.json").write_text(pm_src.read_text(encoding="utf-8"), encoding="utf-8")
    return TestClient(app), tmp_path


def test_user_prompt_to_api_to_forge_pipeline(api_client_p6c):
    """1. User prompt -> API -> ForgePipeline execution test."""
    client, tmp_dir = api_client_p6c
    prompt = "Build an AI task manager application"
    project_id = "proj_p6c_prompt"

    payload = {
        "user_prompt": prompt,
        "project_id": project_id,
        "output_dir": str(tmp_dir),
        "run_immediately": True,
    }

    res = client.post("/api/projects", json=payload)
    assert res.status_code == 201
    data = res.json()

    assert data["project_id"] == project_id
    assert "run_id" in data
    assert data["user_prompt"] == prompt
    assert data["execution_status"] == "COMPLETED"
    assert data["successful_agent_count"] == 7

    # Verify pipeline registered in ACTIVE_PIPELINES
    key = f"{project_id}:{data['run_id']}"
    assert key in ACTIVE_PIPELINES


def test_pipeline_status_retrieval(api_client_p6c):
    """2. Pipeline status retrieval test via API."""
    client, tmp_dir = api_client_p6c
    project_id = "proj_p6c_status"

    create_res = client.post(
        "/api/projects",
        json={
            "user_prompt": "Pipeline status retrieval test",
            "project_id": project_id,
            "output_dir": str(tmp_dir),
            "run_immediately": True,
        },
    )
    assert create_res.status_code == 201
    run_id = create_res.json()["run_id"]

    # Status retrieval for valid run
    res_status = client.get(f"/api/projects/{project_id}/runs/{run_id}")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["project_id"] == project_id
    assert status_data["run_id"] == run_id
    assert status_data["execution_status"] == "COMPLETED"
    assert status_data["successful_agent_count"] == 7

    # Status retrieval for non-existent run
    res_404 = client.get(f"/api/projects/{project_id}/runs/run_non_existent_123")
    assert res_404.status_code == 404
    assert "not found" in res_404.json()["detail"]


def test_seven_agent_status_representation(api_client_p6c):
    """3. Seven-agent status representation test in status response."""
    client, tmp_dir = api_client_p6c
    project_id = "proj_p6c_7agents"

    create_res = client.post(
        "/api/projects",
        json={
            "user_prompt": "Seven-agent representation test",
            "project_id": project_id,
            "output_dir": str(tmp_dir),
            "run_immediately": True,
        },
    )
    run_id = create_res.json()["run_id"]

    res = client.get(f"/api/projects/{project_id}/runs/{run_id}")
    assert res.status_code == 200
    data = res.json()

    expected_stages = ["pm", "ui", "backend", "db", "auth", "qa", "deploy"]
    assert "agent_statuses" in data
    assert len(data["agent_statuses"]) == 7

    for stage in expected_stages:
        assert stage in data["agent_statuses"]
        assert data["agent_statuses"][stage] == "COMPLETED"

    assert data["successful_agent_count"] == 7
    assert data["failed_agent_count"] == 0
    assert set(data["completed_stages"]) == set(expected_stages)


def test_artifact_retrieval_api(api_client_p6c):
    """4. Artifact list and individual artifact retrieval test."""
    client, tmp_dir = api_client_p6c
    project_id = "proj_p6c_artifacts"

    create_res = client.post(
        "/api/projects",
        json={
            "user_prompt": "Artifact retrieval test",
            "project_id": project_id,
            "output_dir": str(tmp_dir),
            "run_immediately": True,
        },
    )
    run_id = create_res.json()["run_id"]
    pm_art_id = create_res.json()["artifact_ids"]["pm"]

    # List all artifacts for run
    res_list = client.get(f"/api/projects/{project_id}/runs/{run_id}/artifacts")
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert list_data["count"] == 7
    assert len(list_data["artifacts"]) == 7

    # Retrieve single artifact by ID
    res_single = client.get(f"/api/artifacts/{pm_art_id}")
    assert res_single.status_code == 200
    art_data = res_single.json()
    assert art_data["artifact_id"] == pm_art_id
    assert art_data["agent_name"] == "pm"
    assert art_data["status"] == "COMPLETED"
    assert "content" in art_data

    # Non-existent artifact ID -> 404
    res_404 = client.get("/api/artifacts/art_non_existent_999")
    assert res_404.status_code == 404


def test_artifact_lineage_api(api_client_p6c):
    """5. Artifact lineage dependency tracking test."""
    client, tmp_dir = api_client_p6c
    project_id = "proj_p6c_lineage"

    create_res = client.post(
        "/api/projects",
        json={
            "user_prompt": "Artifact lineage test",
            "project_id": project_id,
            "output_dir": str(tmp_dir),
            "run_immediately": True,
        },
    )
    run_id = create_res.json()["run_id"]

    res = client.get(f"/api/projects/{project_id}/runs/{run_id}/artifacts")
    assert res.status_code == 200
    artifacts_by_agent = {a["agent_name"]: a for a in res.json()["artifacts"]}

    pm_id = artifacts_by_agent["pm"]["artifact_id"]
    ui_id = artifacts_by_agent["ui"]["artifact_id"]
    backend_id = artifacts_by_agent["backend"]["artifact_id"]
    db_id = artifacts_by_agent["db"]["artifact_id"]
    auth_id = artifacts_by_agent["auth"]["artifact_id"]
    qa_id = artifacts_by_agent["qa"]["artifact_id"]
    deploy_id = artifacts_by_agent["deploy"]["artifact_id"]

    # Verify input_artifacts lineage chains
    assert artifacts_by_agent["pm"]["input_artifacts"] == []
    assert artifacts_by_agent["ui"]["input_artifacts"] == [pm_id]
    assert set(artifacts_by_agent["backend"]["input_artifacts"]) == {pm_id, ui_id}
    assert set(artifacts_by_agent["db"]["input_artifacts"]) == {pm_id, backend_id}
    assert set(artifacts_by_agent["auth"]["input_artifacts"]) == {pm_id, backend_id, db_id}
    assert set(artifacts_by_agent["qa"]["input_artifacts"]) == {pm_id, ui_id, backend_id, db_id, auth_id}
    assert set(artifacts_by_agent["deploy"]["input_artifacts"]) == {pm_id, ui_id, backend_id, db_id, auth_id, qa_id}


def test_monitoring_event_retrieval_api(api_client_p6c):
    """6. Monitoring execution event retrieval test."""
    client, tmp_dir = api_client_p6c
    project_id = "proj_p6c_events"

    create_res = client.post(
        "/api/projects",
        json={
            "user_prompt": "Monitoring event retrieval test",
            "project_id": project_id,
            "output_dir": str(tmp_dir),
            "run_immediately": True,
        },
    )
    run_id = create_res.json()["run_id"]

    res = client.get(f"/api/projects/{project_id}/runs/{run_id}/events")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == project_id
    assert data["run_id"] == run_id
    assert data["count"] >= 23

    event_types = [e["event_type"] for e in data["events"]]
    assert "PIPELINE_STARTED" in event_types
    assert "AGENT_STARTED" in event_types
    assert "ARTIFACT_CREATED" in event_types
    assert "AGENT_COMPLETED" in event_types
    assert "PIPELINE_COMPLETED" in event_types


def test_failed_agent_safe_api_error(api_client_p6c):
    """7. Failed agent stage producing safe API error response test."""
    client, tmp_dir = api_client_p6c
    project_id = "proj_p6c_fail_agent"
    run_id = "run_p6c_fail_agent"

    pipeline = ForgePipeline(
        user_prompt="Failed agent safe API error test app",
        project_id=project_id,
        run_id=run_id,
        output_dir=str(tmp_dir),
    )

    def failing_backend_handler(ctx):
        raise RuntimeError("Database Auth Failed with secret_token=AIzaSy1234567890123456789012345678901 password=supersecretpass")

    pipeline.register_agent_handler(PipelineStage.BACKEND, failing_backend_handler)
    key = f"{project_id}:{run_id}"
    ACTIVE_PIPELINES[key] = pipeline

    # Run pipeline (fails at backend stage)
    pipeline.run_pipeline()

    res = client.get(f"/api/projects/{project_id}/runs/{run_id}")
    assert res.status_code == 200
    data = res.json()

    assert data["execution_status"] == "FAILED"
    assert data["agent_statuses"]["backend"] == "FAILED"
    assert data["failed_agent_count"] == 1

    # Safe error representation with secret sanitization
    assert "backend" in data["error_reports"]
    backend_err = data["error_reports"]["backend"]
    assert "AIzaSy1234567890123456789012345678901" not in backend_err
    assert "supersecretpass" not in backend_err
    assert "[REDACTED_GEMINI_KEY]" in backend_err or "[REDACTED]" in backend_err


def test_failed_artifact_handling_api(api_client_p6c):
    """8. Failed artifact creation and API retrieval test."""
    client, tmp_dir = api_client_p6c
    project_id = "proj_p6c_fail_art"
    run_id = "run_p6c_fail_art"

    pipeline = ForgePipeline(
        user_prompt="Failed artifact handling test app",
        project_id=project_id,
        run_id=run_id,
        output_dir=str(tmp_dir),
    )

    def failing_backend_handler(ctx):
        raise ValueError("Backend build error with api_key=sk-123456789012345678901234")

    pipeline.register_agent_handler(PipelineStage.BACKEND, failing_backend_handler)
    key = f"{project_id}:{run_id}"
    ACTIVE_PIPELINES[key] = pipeline
    pipeline.run_pipeline()

    failed_backend_art_id = pipeline.state.artifact_ids["backend"]
    assert failed_backend_art_id is not None

    # Retrieve artifact via API
    res = client.get(f"/api/artifacts/{failed_backend_art_id}")
    assert res.status_code == 200
    art_data = res.json()
    assert art_data["artifact_id"] == failed_backend_art_id
    assert art_data["status"] == "FAILED"
    assert art_data["agent_name"] == "backend"
    assert "error" in art_data["content"]
    assert "sk-123456789012345678901234" not in art_data["content"]["error"]


def test_rollback_success_api(api_client_p6c):
    """9. Stage rollback success via API test."""
    client, tmp_dir = api_client_p6c
    project_id = "proj_p6c_rb_succ"
    run_id = "run_p6c_rb_succ"

    pipeline = ForgePipeline(
        user_prompt="Rollback success test app",
        project_id=project_id,
        run_id=run_id,
        output_dir=str(tmp_dir),
    )
    pipeline.run_stage(PipelineStage.PM)

    # Register V2 handler for PM stage
    def pm_v2_handler(ctx):
        return {
            "project_name": "TaskFlow V2",
            "description": "Updated PM Spec V2",
            "features": ["Auth V2"],
            "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
            "database_entities": [],
        }

    pipeline.register_agent_handler(PipelineStage.PM, pm_v2_handler)
    pipeline.run_stage(PipelineStage.PM)
    ACTIVE_PIPELINES[f"{project_id}:{run_id}"] = pipeline

    rollback_payload = {
        "agent_name": "pm",
        "target_version": 1,
        "reason": "Reverting PM stage to version 1",
        "force": True,
    }

    res = client.post(f"/api/projects/{project_id}/runs/{run_id}/rollback", json=rollback_payload)
    assert res.status_code == 200
    rb_data = res.json()

    assert rb_data["status"] == "COMPLETED"
    assert rb_data["target_version"] == 1
    assert rb_data["restored_version"] == 3
    assert rb_data["agent_name"] == "pm"
    assert pipeline.state.artifact_ids["pm"] == rb_data["restored_artifact_id"]


def test_rollback_dependency_conflict_api(api_client_p6c):
    """10. Rollback dependency conflict returning HTTP 409 Conflict test."""
    client, tmp_dir = api_client_p6c
    project_id = "proj_p6c_rb_dep"
    run_id = "run_p6c_rb_dep"

    pipeline = ForgePipeline(
        user_prompt="Rollback dependency conflict test app",
        project_id=project_id,
        run_id=run_id,
        output_dir=str(tmp_dir),
    )
    pipeline.run_stage(PipelineStage.PM)
    pipeline.run_stage(PipelineStage.PM)
    pipeline.run_stage(PipelineStage.UI)  # UI stage depends on PM
    ACTIVE_PIPELINES[f"{project_id}:{run_id}"] = pipeline

    rollback_payload = {
        "agent_name": "pm",
        "target_version": 1,
        "force": False,
    }

    res = client.post(f"/api/projects/{project_id}/runs/{run_id}/rollback", json=rollback_payload)
    assert res.status_code == 409
    assert "active downstream dependent artifacts exist for [ui]" in res.json()["detail"]


def test_rollback_invalid_version_api(api_client_p6c):
    """11. Rollback invalid version returning HTTP 400 Bad Request test."""
    client, tmp_dir = api_client_p6c
    project_id = "proj_p6c_rb_inval"
    run_id = "run_p6c_rb_inval"

    pipeline = ForgePipeline(
        user_prompt="Rollback invalid version test app",
        project_id=project_id,
        run_id=run_id,
        output_dir=str(tmp_dir),
    )
    pipeline.run_stage(PipelineStage.PM)
    ACTIVE_PIPELINES[f"{project_id}:{run_id}"] = pipeline

    rollback_payload = {
        "agent_name": "pm",
        "target_version": 999,
        "force": True,
    }

    res = client.post(f"/api/projects/{project_id}/runs/{run_id}/rollback", json=rollback_payload)
    assert res.status_code == 400
    assert "not found" in res.json()["detail"]


def test_secret_sanitization_in_api_responses(api_client_p6c):
    """12. Secret sanitization across status and monitoring event API responses test."""
    client, tmp_dir = api_client_p6c
    gemini_key = "AIzaSy1234567890123456789012345678901"
    password_secret = "secretpass999"
    sensitive_prompt = f"Build task app with GOOGLE_API_KEY={gemini_key} password: {password_secret}"
    project_id = "proj_p6c_secret_san"

    create_res = client.post(
        "/api/projects",
        json={
            "user_prompt": sensitive_prompt,
            "project_id": project_id,
            "output_dir": str(tmp_dir),
            "run_immediately": True,
        },
    )
    assert create_res.status_code == 201
    run_id = create_res.json()["run_id"]

    # Verify status API response redacts sensitive prompt secrets
    res_status = client.get(f"/api/projects/{project_id}/runs/{run_id}")
    assert res_status.status_code == 200
    status_data = res_status.json()

    assert gemini_key not in status_data["user_prompt"]
    assert password_secret not in status_data["user_prompt"]
    assert "[REDACTED_GEMINI_KEY]" in status_data["user_prompt"]

    # Verify events API response redacts sensitive secrets in event messages
    res_events = client.get(f"/api/projects/{project_id}/runs/{run_id}/events")
    assert res_events.status_code == 200
    events_data = res_events.json()

    for evt in events_data["events"]:
        msg = evt.get("message")
        if msg:
            assert gemini_key not in msg
            assert password_secret not in msg
        err_msg = evt.get("error_message")
        if err_msg:
            assert gemini_key not in err_msg
            assert password_secret not in err_msg
