"""Plan preview: see what a refinement would do before anything changes, then apply exactly that plan."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.agents.pm_analysis import analyze_prompt
from backend.schemas.pm_schema import PMOutput
from backend.services.refine_preview import data_warnings

from .test_platform_api import wait_for
from .test_refinement import LIBRARY, build_library, digests


@pytest.fixture
def client(isolated_workspace):
    from backend.main import app

    with TestClient(app) as test_client:
        session = test_client.post("/api/auth/register", json={"email": "owner@forge.test", "password": "owner-pass-1"})
        assert session.status_code == 201, session.text
        test_client.headers.update({"Authorization": f"Bearer {session.json()['access_token']}"})
        yield test_client


def preview(client, pid, text):
    response = client.post(f"/api/projects/{pid}/refine/preview", json={"change_request": text})
    assert response.status_code == 200, response.text
    return response.json()


def test_preview_changes_nothing_and_apply_builds_exactly_the_approved_plan(client, isolated_workspace, monkeypatch):
    pid, first_run = build_library(client)
    project_dir = isolated_workspace / "projects" / pid
    live_before = digests(project_dir / "current")

    shown = preview(client, pid, "Remove the fines module.")
    assert shown["applicable"] and shown["draft_id"].startswith("draft_") and shown["base_version"] == 1
    plan = shown["plan"]
    assert {(c["action"], c["area"], c["target"]) for c in plan["changes"]} >= {("removed", "entity", "Fine")}
    assert {a["agent"]: a["action"] for a in plan["agents"]}["auth"] == "update"
    assert any("fines table" in w for w in shown["warnings"])
    assert shown["migration"]["file"] == "backend/migrations/002_remove_fines_module.sql"
    assert "DROP TABLE IF EXISTS fines CASCADE;" in shown["migration"]["sql"]
    files = shown["files"]
    assert {"backend/app/routers/fines.py", "frontend/src/pages/FinesPage.jsx"} <= set(files["removed"])
    assert "backend/migrations/002_remove_fines_module.sql" in files["added"]

    # nothing changed yet: no new build, same live files, the draft is stored with the project
    project = client.get(f"/api/projects/{pid}").json()
    assert len(project["runs"]) == 1 and project["current_version"] == 1
    assert digests(project_dir / "current") == live_before
    assert (project_dir / "drafts" / f"{shown['draft_id']}.json").is_file()

    # applying uses the stored plan: the PM agent does not interpret the request again
    def must_not_run(*_args, **_kwargs):
        raise AssertionError("the approved plan must be applied as is")

    monkeypatch.setattr("backend.agents.pm_agent.apply_change_request", must_not_run)
    applied = client.post(f"/api/projects/{pid}/refine", json={"draft_id": shown["draft_id"]})
    assert applied.status_code == 202, applied.text
    assert applied.json()["approved_plan"] is True
    summary = wait_for(client, pid, applied.json()["run_id"])
    assert summary["execution_status"] == "COMPLETED", summary.get("error_reports")
    changes = client.get(f"/api/projects/{pid}/runs/{applied.json()['run_id']}/changes").json()
    assert changes["plan"]["summary"] == plan["summary"]
    assert changes["change_request"] == "Remove the fines module."
    assert set(files["removed"]) <= set(changes["files"]["removed"])
    assert set(files["added"]) <= set(changes["files"]["added"])
    assert not (project_dir / "drafts" / f"{shown['draft_id']}.json").exists()
    assert client.post(f"/api/projects/{pid}/refine", json={"draft_id": shown["draft_id"]}).status_code == 404


def test_unclear_requests_are_explained_without_a_draft(client, isolated_workspace):
    pid, _ = build_library(client)
    shown = preview(client, pid, "Make it look nicer please.")
    assert shown["applicable"] is False and shown["draft_id"] is None
    assert "too general" in shown["message"]
    assert not (isolated_workspace / "projects" / pid / "drafts").exists()
    assert client.post(f"/api/projects/{pid}/refine/preview", json={"change_request": "hi"}).status_code == 400


def test_stale_expired_and_unknown_drafts_are_refused(client, isolated_workspace):
    pid, _ = build_library(client)
    colour = preview(client, pid, "Change the primary colour to green.")
    field = preview(client, pid, "Add a membership type (student, staff) to members.")
    applied = client.post(f"/api/projects/{pid}/refine", json={"draft_id": field["draft_id"]}).json()
    assert wait_for(client, pid, applied["run_id"])["execution_status"] == "COMPLETED"

    stale = client.post(f"/api/projects/{pid}/refine", json={"draft_id": colour["draft_id"]})
    assert stale.status_code == 409 and "live version changed" in stale.json()["detail"]

    later = preview(client, pid, "Change the primary colour to green.")
    path = isolated_workspace / "projects" / pid / "drafts" / f"{later['draft_id']}.json"
    data = json.loads(path.read_text())
    data["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    path.write_text(json.dumps(data))
    expired = client.post(f"/api/projects/{pid}/refine", json={"draft_id": later["draft_id"]})
    assert expired.status_code == 409 and "expired" in expired.json()["detail"]

    for bad in ("draft_doesnotexist", "../../project", "x"):
        assert client.post(f"/api/projects/{pid}/refine", json={"draft_id": bad}).status_code == 404


def test_preview_access_rules(client):
    from backend import main

    store = main.services()["store"]
    owner = client.get("/api/auth/me").json()["id"]
    fresh = store.create_project(LIBRARY, owner_id=owner)["project_id"]
    response = client.post(f"/api/projects/{fresh}/refine/preview", json={"change_request": "Add a phone field to members."})
    assert response.status_code == 409 and "no live version" in response.json()["detail"]
    other = store.create_project(LIBRARY, owner_id="someone-else")["project_id"]
    assert client.post(f"/api/projects/{other}/refine/preview",
                       json={"change_request": "Add a phone field to members."}).status_code == 404
    from backend.main import app

    with TestClient(app) as anonymous:
        assert anonymous.post(f"/api/projects/{fresh}/refine/preview", json={"change_request": "x y z z z"}).status_code == 401


def test_data_warnings_cover_every_kind_of_loss():
    before = analyze_prompt(LIBRARY)
    after = PMOutput.model_validate(before.model_dump())
    after.database_entities = [e for e in after.database_entities if e.name != "Fine"]
    loan = next(e for e in after.database_entities if e.name == "Loan")
    status = next(f for f in loan.fields if f.name == "status")
    status.enum_values = [v for v in status.enum_values if v != "overdue"]
    member = next(e for e in after.database_entities if e.name == "Member")
    member.fields = [f for f in member.fields if f.name != "phone"]
    after.user_roles = [r for r in after.user_roles if r.name != "user"]
    warnings = " | ".join(data_warnings(before, after))
    assert "drops the fines table" in warnings
    assert "no longer allows overdue" in warnings
    assert "Member → Phone will be deleted" in warnings
    assert "role 'user'" in warnings
    assert data_warnings(before, before) == []
