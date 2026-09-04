"""Phase 7 Hardening & Reliability Test Suite for FORGE AI."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app, ACTIVE_PIPELINES
from backend.services.pipeline import ForgePipeline, PipelineStage


@pytest.fixture
def api_client_p7(tmp_path):
    """Fixture providing FastAPI TestClient and clearing active pipelines registry with isolated workspace."""
    ACTIVE_PIPELINES.clear()
    return TestClient(app), tmp_path


def test_empty_prompt_validation(api_client_p7):
    """Verify empty or whitespace-only user_prompt returns HTTP 400 Bad Request."""
    client, _ = api_client_p7

    # Empty prompt
    res_empty = client.post("/api/projects", json={"user_prompt": ""})
    assert res_empty.status_code == 400
    assert "user_prompt cannot be empty" in res_empty.json()["detail"]

    # Whitespace prompt
    res_spaces = client.post("/api/projects", json={"user_prompt": "   \n\t  "})
    assert res_spaces.status_code == 400
    assert "user_prompt cannot be empty" in res_spaces.json()["detail"]

    # Empty prompt for PM endpoint
    res_pm = client.post("/api/pm/generate", json={"user_prompt": "   "})
    assert res_pm.status_code == 400
    assert "user_prompt cannot be empty" in res_pm.json()["detail"]


def test_path_traversal_validation(api_client_p7):
    """Verify invalid project_id or output_dir containing path traversal characters returns HTTP 400."""
    client, _ = api_client_p7

    # Path traversal in project_id
    res_proj = client.post(
        "/api/projects",
        json={"user_prompt": "Valid application prompt", "project_id": "../etc/passwd"},
    )
    assert res_proj.status_code == 400
    assert "Invalid project_id" in res_proj.json()["detail"]

    # Path traversal in output_dir
    res_out = client.post(
        "/api/projects",
        json={"user_prompt": "Valid application prompt", "output_dir": "../outputs"},
    )
    assert res_out.status_code == 400
    assert "Invalid output_dir" in res_out.json()["detail"]


def test_non_existent_run_artifacts_404(api_client_p7):
    """Verify requesting artifacts for a non-existent run_id returns HTTP 404 Not Found."""
    client, _ = api_client_p7

    res_404 = client.get("/api/projects/proj_fake/runs/run_fake_9999/artifacts")
    assert res_404.status_code == 404
    assert "not found" in res_404.json()["detail"]


def test_non_existent_run_events_404(api_client_p7):
    """Verify requesting events for a non-existent run_id returns HTTP 404 Not Found."""
    client, _ = api_client_p7

    res_404 = client.get("/api/projects/proj_fake/runs/run_fake_9999/events")
    assert res_404.status_code == 404
    assert "not found" in res_404.json()["detail"]


def test_pipeline_error_sanitization(api_client_p7):
    """Verify pipeline failure redacts embedded secrets in error reports and logged events."""
    client, tmp_dir = api_client_p7
    project_id = "proj_p7_sanitization"
    run_id = "run_p7_sanitization"

    pipeline = ForgePipeline(
        user_prompt="Failure error sanitization app",
        project_id=project_id,
        run_id=run_id,
        output_dir=str(tmp_dir),
    )

    fake_key = "AIzaSy999999999999999999999999999999"
    fake_pass = "supersecretpassword123"

    def failing_handler(ctx):
        raise RuntimeError(f"Connection failed with key={fake_key} password={fake_pass}")

    pipeline.register_agent_handler(PipelineStage.BACKEND, failing_handler)
    key = f"{project_id}:{run_id}"
    ACTIVE_PIPELINES[key] = pipeline

    pipeline.run_pipeline()

    # Verify status response sanitizes error
    status_summary = pipeline.get_status_summary()
    assert status_summary["execution_status"] == "FAILED"
    backend_err = status_summary["error_reports"]["backend"]
    assert fake_key not in backend_err
    assert fake_pass not in backend_err
    assert "[REDACTED_GEMINI_KEY]" in backend_err or "[REDACTED]" in backend_err

    # Verify logging events sanitize error message
    events = pipeline.pipeline_logger.get_events(run_id=run_id)
    failed_evts = [e for e in events if e.event_type.value.endswith("FAILED")]
    for evt in failed_evts:
        if evt.error_message:
            assert fake_key not in evt.error_message
            assert fake_pass not in evt.error_message


def test_cors_headers_handling(api_client_p7):
    """Verify CORS preflight options request returns valid Access-Control-Allow-Origin headers."""
    client, _ = api_client_p7

    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
    }
    res = client.options("/api/projects", headers=headers)
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") in ["http://localhost:3000", "*"]
