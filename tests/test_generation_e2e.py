"""Real seven-agent generation, executed QA and deploy health check (no test doubles)."""

import json
import shutil
from pathlib import Path

import pytest

from backend.config import REPO_ROOT
from backend.services.pipeline import AgentStatus, ForgePipeline, PipelineStage

from .conftest import SHOP_PROMPT, repo_workspace_toolchain_ready


def run(prompt, output_dir, **kwargs):
    pipeline = ForgePipeline(user_prompt=prompt, output_dir=str(output_dir), **kwargs)
    return pipeline, pipeline.run_pipeline()


def test_ecommerce_prompt_generates_and_validates_a_working_app(tmp_path):
    pipeline, state = run(SHOP_PROMPT, tmp_path / "shop", qa_frontend_build=False)
    assert state.execution_status == AgentStatus.COMPLETED, state.error_reports
    app = Path(state.app_dir)
    for rel in ["backend/app/routers/products.py", "backend/app/routers/cart_items.py", "backend/app/routers/orders.py",
                "frontend/src/pages/ProductsPage.jsx", "backend/migrations/001_initial_schema.sql",
                "docker-compose.yml", "README.md", "docs/REQUIREMENTS.md", "forge_manifest.json"]:
        assert (app / rel).is_file(), rel
    qa = state.agent_outputs["qa"]
    assert qa["status"] == "passed" and qa["tests_run"] >= 30 and qa["tests_failed"] == 0
    check_names = {c["name"]: c["status"] for c in qa["checks"]}
    assert check_names["PostgreSQL DDL compilation"] == "passed"
    assert check_names["UI/API contract (frontend calls exist in backend)"] == "passed"
    assert check_names["Frontend production build (vite)"] == "skipped"
    deploy = state.agent_outputs["deploy"]
    assert deploy["status"] == "success" and all(h["status"] == "healthy" for h in deploy["health_checks"])
    manifest = json.loads((app / "forge_manifest.json").read_text(encoding="utf-8"))["files"]
    assert {m["agent"] for m in manifest.values()} == {"pm", "ui", "backend", "db", "auth", "qa", "deploy"}


def test_broken_generated_code_is_reported_not_hidden(tmp_path, monkeypatch):
    """Corrupt the Backend agent's output; QA must fail and Deploy must not run."""
    from backend.codegen import backend_writer

    original = backend_writer.render_entity_router

    def broken_router(bp, entity):
        return original(bp, entity).replace("db.add(obj)", "db.add(obj_that_does_not_exist)")

    monkeypatch.setattr(backend_writer, "render_entity_router", broken_router)
    pipeline, state = run("Build a note taking app with notes and tags", tmp_path / "broken",
                          qa_frontend_build=False, deploy_health_check=False)
    assert state.execution_status == AgentStatus.FAILED
    assert state.agent_statuses[PipelineStage.QA] == AgentStatus.FAILED
    assert state.agent_statuses[PipelineStage.DEPLOY] == AgentStatus.SKIPPED
    report = state.agent_outputs["qa"]
    assert report["status"] == "failed" and report["tests_failed"] > 0
    assert any(e["agent"] == "BackendAgent" for e in report["errors"])
    assert report["repair_recommendation"]


@pytest.mark.skipif(not repo_workspace_toolchain_ready(), reason="Shared frontend toolchain not installed (run the platform once)")
def test_generated_frontend_builds_with_vite():
    out = REPO_ROOT / "workspace" / "_pytest_frontend_build"
    shutil.rmtree(out, ignore_errors=True)
    try:
        pipeline, state = run("A help desk where customers submit support tickets and agents comment", out,
                              qa_frontend_build=True, deploy_health_check=True)
        assert state.execution_status == AgentStatus.COMPLETED, state.error_reports
        assert state.agent_outputs["qa"]["frontend_build"] == "passed"
        assert (Path(state.app_dir) / "frontend" / "dist" / "index.html").is_file()
        assert any(h["endpoint"] == "GET / (frontend bundle)" and h["status"] == "healthy"
                   for h in state.agent_outputs["deploy"]["health_checks"])
    finally:
        shutil.rmtree(out, ignore_errors=True)
