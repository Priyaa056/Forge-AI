"""Project deletion from the project history: permanent, owner-only and limited to the selected project."""

import urllib.error
import urllib.request

import pytest
from fastapi.testclient import TestClient

from .conftest import SHOP_PROMPT, TASK_PROMPT
from .test_platform_api import wait_for


@pytest.fixture
def client(isolated_workspace):
    from backend.main import app

    with TestClient(app) as test_client:
        session = test_client.post("/api/auth/register", json={"email": "owner@forge.test", "password": "owner-pass-1"})
        assert session.status_code == 201, session.text
        test_client.headers.update({"Authorization": f"Bearer {session.json()['access_token']}"})
        yield test_client


def test_delete_removes_only_the_selected_project(client, isolated_workspace):
    first = client.post("/api/projects", json={"user_prompt": TASK_PROMPT}).json()
    pid = first["project_id"]

    # a build that is still running cannot be deleted; nothing changes
    busy = client.delete(f"/api/projects/{pid}")
    assert busy.status_code == 409, busy.text
    assert "still running" in busy.json()["detail"]
    assert wait_for(client, pid, first["run_id"])["execution_status"] == "COMPLETED"

    second = client.post("/api/projects", json={"user_prompt": SHOP_PROMPT}).json()
    other = second["project_id"]
    assert wait_for(client, other, second["run_id"])["execution_status"] == "COMPLETED"

    project_dir = isolated_workspace / "projects" / pid
    artifact_dir = isolated_workspace / "artifacts" / pid
    other_files = sorted(p.relative_to(isolated_workspace) for p in (isolated_workspace / "projects" / other).rglob("*"))
    other_artifacts = sorted(p.name for p in (isolated_workspace / "artifacts" / other).glob("*.json"))
    assert project_dir.is_dir() and len(list(artifact_dir.glob("*.json"))) >= 7 and other_artifacts

    preview = client.post(f"/api/projects/{pid}/preview/start").json()
    assert preview["running"]

    deleted = client.delete(f"/api/projects/{pid}")
    assert deleted.status_code == 200, deleted.text
    body = deleted.json()
    assert body["deleted"] is True and body["project_id"] == pid and body["artifacts_removed"] >= 7

    # permanently gone: history, files, artifacts, preview
    assert [p["project_id"] for p in client.get("/api/projects").json()["projects"]] == [other]
    assert client.get(f"/api/projects/{pid}").status_code == 404
    assert client.get(f"/api/projects/{pid}/runs/{first['run_id']}").status_code == 404
    assert client.delete(f"/api/projects/{pid}").status_code == 404
    assert not project_dir.exists() and not artifact_dir.exists()
    assert not any((isolated_workspace / ".trash").iterdir())
    with pytest.raises((urllib.error.URLError, ConnectionError, OSError)):
        urllib.request.urlopen(preview["url"] + "/health", timeout=3)

    # the other project is untouched
    assert sorted(p.relative_to(isolated_workspace) for p in (isolated_workspace / "projects" / other).rglob("*")) == other_files
    assert sorted(p.name for p in (isolated_workspace / "artifacts" / other).glob("*.json")) == other_artifacts
    assert client.get(f"/api/projects/{other}").status_code == 200
    assert client.get(f"/api/projects/{other}/runs/current/files").json()["count"] > 0

    # a fresh API process (page refresh / restart) does not bring the project back
    from backend import main

    main.reset_services()
    assert [p["project_id"] for p in client.get("/api/projects").json()["projects"]] == [other]


def test_only_the_owner_can_delete(client, isolated_workspace):
    from backend import main

    project = main.services()["store"].create_project(TASK_PROMPT, owner_id="someone-else")
    response = client.delete(f"/api/projects/{project['project_id']}")
    assert response.status_code == 404  # other users' projects are invisible
    assert (isolated_workspace / "projects" / project["project_id"] / "project.json").is_file()
    assert client.delete("/api/projects/not a valid id").status_code == 404
    assert client.delete("/api/projects/..").status_code == 404


def test_delete_requires_authentication(isolated_workspace):
    from backend.main import app

    with TestClient(app) as anonymous:
        assert anonymous.delete("/api/projects/proj_0123456789").status_code == 401
