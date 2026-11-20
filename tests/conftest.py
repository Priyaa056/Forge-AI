"""Shared fixtures for the FORGE AI platform test-suite.

Test doubles (fake LLM clients, stub QA/Deploy handlers) are defined here and are used only by tests;
the real execution path never uses them.
"""

import os
from pathlib import Path
from typing import Any, Dict

import pytest

from backend.agents.auth_agent import AuthAgent
from backend.agents.backend_agent import BackendAgent
from backend.agents.db_agent import DBAgent
from backend.agents.pm_agent import PMAgent
from backend.agents.ui_agent import UIAgent
from backend.llm.client import set_llm_client
from backend.schemas.deploy_schema import DeployOutput
from backend.schemas.qa_schema import QAOutput
from backend.services.pipeline import ForgePipeline, PipelineStage

TASK_PROMPT = ("Build a task management application with user registration, login, task creation, task editing, "
               "task deletion, categories, task status and an admin dashboard.")
SHOP_PROMPT = ("Build an e-commerce website with user registration, login, product listings, product search, "
               "shopping cart, order management and an admin dashboard.")


@pytest.fixture(autouse=True)
def _test_environment(monkeypatch):
    """Deterministic, fast defaults: no real LLM, no frontend build unless a test opts in."""
    monkeypatch.setenv("USE_LLM", "false")
    monkeypatch.setenv("FORGE_QA_FRONTEND_BUILD", "false")
    for name in ("LLM_PROVIDER", "GROQ_API_KEY", "GROQ_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
                 "LLM_MAX_TOKENS"):
        monkeypatch.delenv(name, raising=False)  # a developer's backend/.env must not change test results
    set_llm_client(None, force=False)
    yield
    set_llm_client(None, force=False)


class FakeLLM:
    """Test double for the Gemini client: returns queued responses (or raises queued exceptions)."""

    name = "fake-llm"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []

    def generate_text(self, prompt: str, *, json_mode: bool = True) -> str:
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("FakeLLM received more calls than expected")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def fake_llm():
    def install(*responses):
        client = FakeLLM(*responses)
        set_llm_client(client)
        return client
    return install


def _spec_only(agent_cls):
    """Handler that runs a real agent in spec-only mode (no files) against the run's artifact context."""
    def handler(ctx: Dict[str, Any]) -> Dict[str, Any]:
        kwargs = {"artifact_context": ctx["artifact_context"],
                  "output_filepath": str(Path(ctx["output_dir"]) / f"{agent_cls.__name__}.json")}
        if agent_cls is PMAgent:
            kwargs["user_prompt"] = ctx["user_prompt"]
        return agent_cls(**kwargs).run().model_dump()
    return handler


def qa_test_double(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return QAOutput(project_name="test", status="passed", tests_run=1, tests_passed=1, deployment_ready=True,
                    summary="TEST DOUBLE - not an executed QA run").model_dump()


def deploy_test_double(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return DeployOutput(project_name="test", status="success", deployment_ready=True,
                        logs=["TEST DOUBLE - no deployment performed"]).model_dump()


@pytest.fixture
def fast_pipeline(tmp_path):
    """Factory for pipelines whose agents run spec-only (fast) with QA/Deploy test doubles."""
    def make(prompt: str = TASK_PROMPT, **kwargs) -> ForgePipeline:
        handlers = {
            PipelineStage.PM: _spec_only(PMAgent),
            PipelineStage.UI: _spec_only(UIAgent),
            PipelineStage.BACKEND: _spec_only(BackendAgent),
            PipelineStage.DB: _spec_only(DBAgent),
            PipelineStage.AUTH: _spec_only(AuthAgent),
            PipelineStage.QA: qa_test_double,
            PipelineStage.DEPLOY: deploy_test_double,
        }
        handlers.update(kwargs.pop("handlers", {}))
        kwargs.setdefault("output_dir", str(tmp_path / f"run_{len(list(tmp_path.iterdir()))}"))
        return ForgePipeline(user_prompt=prompt, generate_code=False, agent_handlers=handlers, **kwargs)
    return make


@pytest.fixture
def isolated_workspace(tmp_path, monkeypatch):
    """Point the platform at a throw-away workspace and reset API service singletons."""
    from backend import main

    ws = tmp_path / "workspace"
    monkeypatch.setenv("FORGE_WORKSPACE", str(ws))
    main.reset_services()
    yield ws
    main.reset_services()


def repo_workspace_toolchain_ready() -> bool:
    from backend.services import toolchain

    return toolchain.is_ready()


os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
