"""Platform API end-to-end: projects, background runs, monitoring, artifacts, files, rollback and preview.

These tests run the real seven-agent pipeline (QA executes the generated test-suite; the frontend
build is disabled for speed and covered in test_generation_e2e.py).
"""

import io
import json
import time
import urllib.request
import zipfile

import pytest
from fastapi.testclient import TestClient

from .conftest import TASK_PROMPT


@pytest.fixture
def client(isolated_workspace):
    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client


def wait_for(client, pid, rid, timeout=240):
    deadline = time.time() + timeout
    while time.time() < deadline:
        summary = client.get(f"/api/projects/{pid}/runs/{rid}").json()
        status = summary.get("execution_status")
        if status == "FAILED" or (status == "COMPLETED" and summary.get("promotion", {}).get("state") != "pending"):
            return summary
        time.sleep(0.3)
    raise AssertionError("run did not finish in time")


def test_system_and_validation(client):
    system = client.get("/api/system").json()
    assert system["llm"]["mode"] == "deterministic"
    assert [a["name"] for a in system["agents"]] == ["pm", "ui", "backend", "db", "auth", "qa", "deploy"]
    response = client.post("/api/projects", json={"user_prompt": "app"})
    assert response.status_code == 400 and "too short" in response.json()["detail"]
    assert client.post("/api/projects", json={"user_prompt": TASK_PROMPT, "simulate_failure": "nope"}).status_code == 400
    assert client.get("/api/projects/proj_doesnotexist").status_code == 404


def test_full_lifecycle_generation_failure_recovery_and_rollback(client):
    created = client.post("/api/projects", json={"user_prompt": TASK_PROMPT})
    assert created.status_code == 202
    pid, rid1 = created.json()["project_id"], created.json()["run_id"]

    summary = wait_for(client, pid, rid1)
    assert summary["execution_status"] == "COMPLETED", summary["error_reports"]
    assert summary["promotion"] == {"state": "promoted", "version": 1}
    assert summary["qa_summary"]["status"] == "passed" and summary["qa_summary"]["tests_run"] >= 20
    assert all(a["status"] == "COMPLETED" for a in summary["agents"].values())

    # Monitoring: incremental events and agent logs
    events = client.get(f"/api/projects/{pid}/runs/{rid1}/events").json()["events"]
    types = {e["event_type"] for e in events}
    assert {"PIPELINE_STARTED", "AGENT_LOG", "ARTIFACT_CREATED", "PIPELINE_COMPLETED", "VERSION_PROMOTED"} <= types
    tail = client.get(f"/api/projects/{pid}/runs/{rid1}/events", params={"after": events[-3]["event_id"]}).json()
    assert tail["count"] == 2

    # Artifacts and specs
    artifacts = client.get(f"/api/projects/{pid}/runs/{rid1}/artifacts").json()["artifacts"]
    assert {a["agent_name"] for a in artifacts} == {"pm", "ui", "backend", "db", "auth", "qa", "deploy"}
    qa_art = client.get(f"/api/artifacts/{summary['artifact_ids']['qa']}").json()
    assert qa_art["content"]["tests_passed"] == qa_art["content"]["tests_run"]
    deploy = client.get(f"/api/projects/{pid}/runs/{rid1}/specs/deploy").json()
    assert deploy["deployment_ready"] and any(h["endpoint"] == "GET /health" and h["status"] == "healthy" for h in deploy["health_checks"])
    assert deploy["container_build_verified"] is False

    # Files of the generated application
    files = client.get(f"/api/projects/{pid}/runs/current/files").json()["files"]
    agents = {f["agent"] for f in files if f["agent"]}
    assert agents == {"pm", "ui", "backend", "db", "auth", "qa", "deploy"}
    content = client.get(f"/api/projects/{pid}/runs/current/files/content", params={"path": "backend/app/routers/tasks.py"})
    assert content.status_code == 200 and "require_permission" in content.json()["content"]
    assert client.get(f"/api/projects/{pid}/runs/current/files/content", params={"path": "../project.json"}).status_code == 404
    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/api/projects/{pid}/runs/current/download").content))
    assert "backend/app/main.py" in archive.namelist()

    # Preview: the generated app runs as a real process
    preview = client.post(f"/api/projects/{pid}/preview/start").json()
    assert preview["running"] and preview["url"].startswith("http://127.0.0.1:")
    try:
        health = json.loads(urllib.request.urlopen(preview["url"] + "/health", timeout=10).read())
        assert health["status"] == "healthy"
        login = urllib.request.Request(preview["url"] + "/api/auth/login", method="POST",
                                       data=json.dumps({"email": preview["admin_email"], "password": preview["admin_password"]}).encode(),
                                       headers={"Content-Type": "application/json"})
        assert json.loads(urllib.request.urlopen(login, timeout=10).read())["user"]["role"] == "admin"
    finally:
        client.post(f"/api/projects/{pid}/preview/stop")
    assert client.get(f"/api/projects/{pid}/preview").json()["running"] is False

    # A failing iteration does not replace the stable version
    failed = client.post(f"/api/projects/{pid}/runs", json={"user_prompt": TASK_PROMPT + " Add task priority.", "simulate_failure": "auth"}).json()
    failed_summary = wait_for(client, pid, failed["run_id"])
    assert failed_summary["execution_status"] == "FAILED"
    assert failed_summary["agents"]["auth"]["status"] == "FAILED"
    assert [failed_summary["agents"][s]["status"] for s in ("qa", "deploy")] == ["SKIPPED", "SKIPPED"]
    project = client.get(f"/api/projects/{pid}").json()
    assert project["current_run_id"] == rid1 and project["current_version"] == 1
    assert client.post(f"/api/projects/{pid}/rollback", json={"target_run_id": failed["run_id"]}).status_code == 409

    # A second successful iteration with a different app, then roll back to version 1
    second = client.post(f"/api/projects/{pid}/runs", json={"user_prompt": "Build a recipe book with recipes, categories and reviews"}).json()
    assert wait_for(client, pid, second["run_id"])["execution_status"] == "COMPLETED"
    paths = {f["path"] for f in client.get(f"/api/projects/{pid}/runs/current/files").json()["files"]}
    assert "backend/app/routers/recipes.py" in paths

    rollback = client.post(f"/api/projects/{pid}/rollback", json={"target_run_id": rid1, "reason": "test"})
    assert rollback.status_code == 200 and rollback.json()["restored_from_version"] == 1
    paths = {f["path"] for f in client.get(f"/api/projects/{pid}/runs/current/files").json()["files"]}
    assert "backend/app/routers/tasks.py" in paths and "backend/app/routers/recipes.py" not in paths
    project = client.get(f"/api/projects/{pid}").json()
    assert [v["source"] for v in project["versions"]] == ["run", "run", "rollback"]
    assert "preview_admin" not in project
    project_events = {e["event_type"] for e in client.get(f"/api/projects/{pid}/events").json()["events"]}
    assert {"ROLLBACK_STARTED", "ROLLBACK_COMPLETED"} <= project_events
