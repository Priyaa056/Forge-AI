"""Iterative refinement end to end: change plan -> only affected agents -> QA with regression check -> new version."""

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .test_platform_api import wait_for

LIBRARY = ("Build a library management system with members, books, loans with due dates, fines for late returns "
           "and an admin dashboard showing overdue loans.")


@pytest.fixture
def client(isolated_workspace):
    from backend.main import app

    with TestClient(app) as test_client:
        session = test_client.post("/api/auth/register", json={"email": "owner@forge.test", "password": "owner-pass-1"})
        assert session.status_code == 201, session.text
        test_client.headers.update({"Authorization": f"Bearer {session.json()['access_token']}"})
        yield test_client


def digests(root: Path):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and not ({"node_modules", "dist", "__pycache__", ".pytest_cache",
                                                              ".forge_runtime"} & set(p.relative_to(root).parts))}


def build_library(client):
    created = client.post("/api/projects", json={"user_prompt": LIBRARY}).json()
    summary = wait_for(client, created["project_id"], created["run_id"])
    assert summary["execution_status"] == "COMPLETED", summary.get("error_reports")
    return created["project_id"], created["run_id"]


def refine(client, pid, text):
    response = client.post(f"/api/projects/{pid}/refine", json={"change_request": text})
    assert response.status_code == 202, response.text
    started = response.json()
    assert started["mode"] == "refine"
    return started["run_id"], wait_for(client, pid, started["run_id"])


def test_refinements_change_only_what_was_asked(client, isolated_workspace):
    pid, first_run = build_library(client)
    store_root = isolated_workspace / "projects" / pid
    v1 = digests(store_root / "runs" / first_run / "app")

    # 1. colour only: only the UI agent rewrites files; Backend/DB/Auth are reused from v1
    run2, summary = refine(client, pid, "Change the primary colour to green.")
    assert summary["execution_status"] == "COMPLETED" and summary["promotion"] == {"state": "promoted", "version": 2}
    agents = summary["agents"]
    assert {s: agents[s]["generation_mode"] for s in ("backend", "db", "auth")} == dict.fromkeys(("backend", "db", "auth"), "reused")
    assert agents["auth"]["reused_from_version"] == 1
    changes = client.get(f"/api/projects/{pid}/runs/{run2}/changes").json()
    assert changes["base_version"] == 1 and changes["change_request"] == "Change the primary colour to green."
    assert {a["agent"]: a["action"] for a in changes["plan"]["agents"]}["ui"] == "update"
    v2 = digests(store_root / "runs" / run2 / "app")
    changed = {p for p in set(v1) | set(v2) if v1.get(p) != v2.get(p)} - {"forge_manifest.json"}
    # README lists the project's files, so the new CHANGELOG appears there too
    assert changed == {"frontend/src/styles.css", "docs/REQUIREMENTS.md", "docs/CHANGELOG.md", "README.md"}
    assert set(changes["files"]["modified"]) | set(changes["files"]["added"]) == changed
    assert changes["regression"]["failures"] == [] and changes["regression"]["requirements_checked"] > 40
    assert "#16a34a" in (store_root / "current" / "frontend" / "src" / "styles.css").read_text()

    # 2. a new field: a new migration evolves the schema, earlier migrations are untouched
    run3, summary = refine(client, pid, "Add a membership type (student, staff, public) to members.")
    assert summary["execution_status"] == "COMPLETED", summary.get("error_reports")
    assert summary["agents"]["auth"]["generation_mode"] == "reused"
    app3 = store_root / "runs" / run3 / "app"
    migrations = sorted(p.name for p in (app3 / "backend" / "migrations").glob("*.sql"))
    assert migrations == ["001_initial_schema.down.sql", "001_initial_schema.sql",
                          "002_add_membership_type_student_staff.down.sql", "002_add_membership_type_student_staff.sql"]
    assert digests(app3)["backend/migrations/001_initial_schema.sql"] == v1["backend/migrations/001_initial_schema.sql"]
    sql = (app3 / "backend" / "migrations" / "002_add_membership_type_student_staff.sql").read_text()
    assert "ALTER TABLE members ADD COLUMN IF NOT EXISTS membership_type" in sql
    assert "002_add_membership_type_student_staff.sql:/docker-entrypoint-initdb.d/" in (app3 / "docker-compose.yml").read_text()
    assert "membership_type" in (app3 / "backend" / "app" / "models.py").read_text()
    changelog = (app3 / "docs" / "CHANGELOG.md").read_text()
    assert changelog.index("membership type") < changelog.index("primary colour")  # newest first

    # 3. remove a module: its page, API and tests disappear; everything else still passes (regression check)
    run4, summary = refine(client, pid, "Remove the fines module.")
    assert summary["execution_status"] == "COMPLETED", summary.get("error_reports")
    current = store_root / "current"
    for gone in ("backend/app/routers/fines.py", "backend/tests/test_fines.py", "frontend/src/pages/FinesPage.jsx"):
        assert not (current / gone).exists(), gone
    changes = client.get(f"/api/projects/{pid}/runs/{run4}/changes").json()
    assert {"backend/app/routers/fines.py", "backend/tests/test_fines.py"} <= set(changes["files"]["removed"])
    regression = changes["regression"]
    assert regression["failures"] == [] and regression["requirements_retired"] > 0 and regression["tests_checked"] > 30
    assert "DROP TABLE IF EXISTS fines" in (current / "backend" / "migrations" / "003_remove_fines_module.sql").read_text()

    # history: every refinement is a version; the project list shows the modes
    project = client.get(f"/api/projects/{pid}").json()
    assert project["current_version"] == 4
    assert [r["mode"] for r in project["runs"]] == ["build", "refine", "refine", "refine"]
    assert [r["base_version"] for r in project["runs"]] == [None, 1, 2, 3]

    # rollback to v1 restores the original files exactly
    rolled = client.post(f"/api/projects/{pid}/rollback", json={"target_run_id": first_run})
    assert rolled.status_code == 200, rolled.text
    assert {k: v for k, v in digests(current).items() if k != "forge_manifest.json"} == \
        {k: v for k, v in v1.items() if k != "forge_manifest.json"}


def test_unclear_or_impossible_requests_keep_the_live_version(client):
    pid, _ = build_library(client)
    run, summary = refine(client, pid, "Make it look nicer please.")
    assert summary["execution_status"] == "FAILED"
    assert "too general" in summary["error_reports"]["pm"] and "current version stays live" in summary["error_reports"]["pm"]
    assert summary["agents"]["ui"]["status"] == "SKIPPED"
    assert client.get(f"/api/projects/{pid}").json()["current_version"] == 1

    run, summary = refine(client, pid, "Add online payments for fines.")
    assert summary["execution_status"] == "FAILED" and "Online payment" in summary["error_reports"]["pm"]


def test_impact_check_runs_an_agent_the_plan_wrongly_reused(client, monkeypatch):
    from backend.agents import change_plan

    pid, _ = build_library(client)
    monkeypatch.setitem(change_plan.AREA_AGENTS, "workflow", {"ui", "backend", "db"})  # simulate a planning gap
    run, summary = refine(client, pid, "Add a 'lost' status to loans.")
    assert summary["execution_status"] == "COMPLETED", summary.get("error_reports")
    assert [e["agent"] for e in summary["refinement"]["escalated"]] == ["auth"]
    assert summary["agents"]["auth"]["generation_mode"] != "reused"
    assert summary["refinement"]["agent_actions"]["auth"] == "update (impact check)"


def test_refine_validation_and_access(client):
    from backend import main

    store = main.services()["store"]
    owner = client.get("/api/auth/me").json()["id"]
    fresh = store.create_project(LIBRARY, owner_id=owner)["project_id"]
    response = client.post(f"/api/projects/{fresh}/refine", json={"change_request": "Add a phone field to members."})
    assert response.status_code == 409 and "no live version" in response.json()["detail"]
    assert client.post(f"/api/projects/{fresh}/refine", json={"change_request": "hi"}).status_code == 400
    other = store.create_project(LIBRARY, owner_id="someone-else")["project_id"]
    assert client.post(f"/api/projects/{other}/refine", json={"change_request": "Add a phone field to members."}).status_code == 404

    pid, run_id = build_library(client)
    assert client.get(f"/api/projects/{pid}/runs/{run_id}/changes").status_code == 404  # a normal build
    started = client.post(f"/api/projects/{pid}/refine", json={"change_request": "Change the primary colour to green."}).json()
    busy = client.post(f"/api/projects/{pid}/refine", json={"change_request": "Change the primary colour to red."})
    assert busy.status_code == 409 and "already running" in busy.json()["detail"]
    wait_for(client, pid, started["run_id"])

    from backend.main import app

    with TestClient(app) as anonymous:
        assert anonymous.post(f"/api/projects/{pid}/refine", json={"change_request": "x y z z z"}).status_code == 401
