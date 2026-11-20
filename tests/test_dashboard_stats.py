"""Dashboard data: per-user analytics (GET /api/stats) and the richer project list behind the cards."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.services.insights import user_stats
from backend.services.project_store import ProjectStore

from .test_platform_api import wait_for
from .test_refinement import LIBRARY


@pytest.fixture
def client(isolated_workspace):
    from backend.main import app

    with TestClient(app) as test_client:
        session = test_client.post("/api/auth/register", json={"email": "owner@forge.test", "password": "owner-pass-1"})
        assert session.status_code == 201, session.text
        test_client.headers.update({"Authorization": f"Bearer {session.json()['access_token']}"})
        yield test_client


def test_stats_for_a_new_account(client):
    stats = client.get("/api/stats").json()
    assert stats["projects"] == 0 and stats["builds"] == 0 and stats["success_rate"] is None
    assert stats["avg_build_ms"] is None and len(stats["daily"]) == 14
    assert client.get("/api/stats?days=30").json()["days"] == 30
    assert client.get("/api/stats?days=3").status_code == 422


def test_stats_and_cards_reflect_real_builds(client):
    ok = client.post("/api/projects", json={"user_prompt": LIBRARY}).json()
    assert wait_for(client, ok["project_id"], ok["run_id"])["execution_status"] == "COMPLETED"
    refined = client.post(f"/api/projects/{ok['project_id']}/refine",
                          json={"change_request": "Change the primary colour to green."}).json()
    assert wait_for(client, ok["project_id"], refined["run_id"])["execution_status"] == "COMPLETED"
    bad = client.post("/api/projects", json={"user_prompt": LIBRARY, "simulate_failure": "qa"}).json()
    assert wait_for(client, bad["project_id"], bad["run_id"])["execution_status"] == "FAILED"

    stats = client.get("/api/stats").json()
    assert (stats["projects"], stats["live_apps"], stats["builds"], stats["succeeded"], stats["failed"]) == (2, 1, 3, 2, 1)
    assert stats["refinements"] == 1 and stats["success_rate"] == pytest.approx(66.7)
    assert stats["avg_build_ms"] > 0 and stats["tests_passed"] >= 100 and stats["tests_run"] >= stats["tests_passed"]
    assert stats["daily"][-1]["builds"] == 3 and stats["daily"][-1]["succeeded"] == 2 and stats["daily"][-1]["failed"] == 1
    assert stats["agent_avg_ms"]["qa"] > 0 and stats["agent_avg_ms"]["pm"] is not None
    # every build is from today: there is no previous week to compare with, so no change is reported
    assert stats["builds_change_pct"] is None and stats["success_rate_change"] is None

    cards = {p["project_id"]: p for p in client.get("/api/projects").json()["projects"]}
    live = cards[ok["project_id"]]
    assert live["refinements"] == 1 and live["theme_color"] == "#16a34a"
    assert live["modules"] == ["Members", "Books", "Loans", "Fines"]
    assert live["last_run"]["mode"] == "refine" and live["last_run"]["duration_ms"] > 0
    assert set(live["last_run"]["agents"]) == {"pm", "ui", "backend", "db", "auth", "qa", "deploy"}
    assert live["last_run"]["agents"]["backend"] == {"status": "COMPLETED", "reused": True}
    assert live["last_run"]["qa"]["passed"] == live["last_run"]["qa"]["run"] > 0
    failed = cards[bad["project_id"]]
    assert failed["last_run"]["agents"]["qa"]["status"] == "FAILED"
    assert failed["last_run"]["agents"]["deploy"]["status"] == "SKIPPED" and failed["refinements"] == 0


def test_stats_are_per_user_and_by_day(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    mine = store.create_project(LIBRARY, owner_id="me")["project_id"]
    other = store.create_project(LIBRARY, owner_id="other")["project_id"]
    plan = [(mine, "run_a01", "2026-11-19T10:00:00+00:00", "COMPLETED", 8000, 50, None),
            (mine, "run_a02", "2026-11-19T11:00:00+00:00", "FAILED", None, 0, None),
            (mine, "run_a03", "2026-11-12T09:00:00+00:00", "COMPLETED", 12000, 40, "refine"),
            (mine, "run_a04", "2026-11-01T09:00:00+00:00", "COMPLETED", 5000, 10, None),  # outside the 14 days
            (other, "run_b01", "2026-11-19T10:00:00+00:00", "COMPLETED", 1000, 99, None)]
    for pid, rid, created, status, ms, tests, mode in plan:
        path = store.register_run(pid, rid, "x", {"mode": mode} if mode else {}) / "run.json"
        data = json.loads(path.read_text())
        data.update(created_at=created, execution_status=status, summary={
            "execution_status": status, "total_duration_ms": ms,
            "qa_summary": {"tests_passed": tests, "tests_run": tests} if tests else None,
            "agents": {"qa": {"duration_ms": 3000, "generation_mode": "execution"},
                       "auth": {"duration_ms": 30, "generation_mode": "reused"}}})
        path.write_text(json.dumps(data))

    stats = user_stats(store, "me", days=14, today=date(2026, 11, 20))
    assert stats["builds"] == 4 and stats["succeeded"] == 3 and stats["failed"] == 1 and stats["refinements"] == 1
    assert stats["tests_passed"] == 100 and stats["avg_build_ms"] == pytest.approx(25000 / 3, rel=1e-3)
    assert stats["agent_avg_ms"]["qa"] == 3000 and stats["agent_avg_ms"]["auth"] is None  # reused agents excluded
    by_day = {d["date"]: d for d in stats["daily"]}
    assert by_day["2026-11-19"] == {"date": "2026-11-19", "builds": 2, "succeeded": 1, "failed": 1, "success_rate": 50.0,
                                    "avg_build_ms": 8000.0, "tests_passed": 50}
    assert by_day["2026-11-12"]["succeeded"] == 1 and "2026-11-01" not in by_day
    assert stats["daily"][0]["date"] == "2026-11-07" and stats["daily"][-1]["date"] == "2026-11-20"
    # last 7 days: 2 builds (50 % success) vs previous 7 days: 1 build (100 %)
    assert stats["builds_change_pct"] == 100.0 and stats["success_rate_change"] == -50.0
