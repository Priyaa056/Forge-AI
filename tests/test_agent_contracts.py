"""Agents validate the structured contracts they consume and fail loudly on inconsistencies."""

import json

import pytest

from backend.agents.auth_agent import AuthAgent
from backend.agents.backend_agent import BackendAgent
from backend.agents.db_agent import DBAgent
from backend.agents.deploy_agent import DeployAgent
from backend.agents.pm_agent import PMAgent
from backend.agents.qa_agent import QAAgent
from backend.agents.ui_agent import UIAgent
from backend.codegen.project_files import GeneratedProject
from backend.exceptions import GenerationError, MissingInputError, ValidationError

from .conftest import TASK_PROMPT


@pytest.fixture
def specs(tmp_path):
    paths = {name: tmp_path / f"{name}.json" for name in ("pm", "ui", "backend", "db", "auth", "qa")}
    PMAgent(user_prompt=TASK_PROMPT, output_filepath=str(paths["pm"])).run()
    UIAgent(pm_output_path=str(paths["pm"]), output_filepath=str(paths["ui"])).run()
    BackendAgent(pm_output_path=str(paths["pm"]), ui_output_path=str(paths["ui"]), output_filepath=str(paths["backend"])).run()
    DBAgent(pm_output_path=str(paths["pm"]), backend_output_path=str(paths["backend"]), output_filepath=str(paths["db"])).run()
    return paths


def test_spec_only_chain_produces_consistent_contracts(specs):
    auth = AuthAgent(pm_output_path=str(specs["pm"]), backend_output_path=str(specs["backend"]),
                     db_output_path=str(specs["db"]), output_filepath=str(specs["auth"])).run()
    api = json.loads(specs["backend"].read_text())
    assert api["ui_contract_coverage"]["missing"] == []
    assert {r.role_name for r in auth.rbac_roles} == {"admin", "user"}
    db = json.loads(specs["db"].read_text())
    assert {t["model_name"] for t in db["tables"]} == {"User", "Category", "Task"}


def test_backend_agent_rejects_ui_requirements_it_cannot_serve(specs):
    ui = json.loads(specs["ui"].read_text())
    ui["api_requirements"].append({"endpoint": "/api/reports/export", "method": "GET", "description": "Export"})
    specs["ui"].write_text(json.dumps(ui))
    with pytest.raises(ValidationError, match="/api/reports/export"):
        BackendAgent(pm_output_path=str(specs["pm"]), ui_output_path=str(specs["ui"]),
                     output_filepath=str(specs["backend"])).run()


def test_db_agent_rejects_api_fields_without_columns(specs):
    api = json.loads(specs["backend"].read_text())
    create = next(ep for ep in api["endpoints"] if ep["method"] == "POST" and ep["path"] == "/api/tasks")
    create["request_schema"]["fields"].append({"name": "estimated_hours", "type": "int", "required": False})
    specs["backend"].write_text(json.dumps(api))
    with pytest.raises(ValidationError, match="estimated_hours"):
        DBAgent(pm_output_path=str(specs["pm"]), backend_output_path=str(specs["backend"]),
                output_filepath=str(specs["db"])).run()


def test_auth_agent_requires_security_columns(specs):
    db = json.loads(specs["db"].read_text())
    users = next(t for t in db["tables"] if t["model_name"] == "User")
    users["columns"] = [c for c in users["columns"] if c["name"] != "hashed_password"]
    specs["db"].write_text(json.dumps(db))
    with pytest.raises(ValidationError, match="hashed_password"):
        AuthAgent(pm_output_path=str(specs["pm"]), backend_output_path=str(specs["backend"]),
                  db_output_path=str(specs["db"]), output_filepath=str(specs["auth"])).run()


def test_auth_agent_rejects_unknown_roles(specs):
    api = json.loads(specs["backend"].read_text())
    api["endpoints"][0]["required_roles"] = ["superhero"]
    specs["backend"].write_text(json.dumps(api))
    with pytest.raises(ValidationError, match="superhero"):
        AuthAgent(pm_output_path=str(specs["pm"]), backend_output_path=str(specs["backend"]),
                  db_output_path=str(specs["db"]), output_filepath=str(specs["auth"])).run()


def test_missing_upstream_input_is_reported(tmp_path):
    with pytest.raises(MissingInputError):
        UIAgent(pm_output_path=str(tmp_path / "missing.json"), output_filepath=str(tmp_path / "ui.json")).run()


def test_qa_agent_refuses_to_report_without_generated_project(specs):
    AuthAgent(pm_output_path=str(specs["pm"]), backend_output_path=str(specs["backend"]),
              db_output_path=str(specs["db"]), output_filepath=str(specs["auth"])).run()
    agent = QAAgent(pm_output_path=str(specs["pm"]), backend_output_path=str(specs["backend"]),
                    db_output_path=str(specs["db"]), auth_output_path=str(specs["auth"]),
                    ui_output_path=str(specs["ui"]), output_filepath=str(specs["qa"]))
    with pytest.raises(GenerationError, match="refusing"):
        agent.run()


def test_deploy_agent_refuses_untested_build(specs, tmp_path):
    AuthAgent(pm_output_path=str(specs["pm"]), backend_output_path=str(specs["backend"]),
              db_output_path=str(specs["db"]), output_filepath=str(specs["auth"])).run()
    specs["qa"].write_text(json.dumps({"status": "failed", "tests_run": 3, "tests_failed": 1}))
    agent = DeployAgent(pm_output_path=str(specs["pm"]), backend_output_path=str(specs["backend"]),
                        auth_output_path=str(specs["auth"]), qa_output_path=str(specs["qa"]),
                        output_filepath=str(tmp_path / "deploy.json"), project=GeneratedProject(tmp_path / "app"))
    with pytest.raises(GenerationError, match="QA status"):
        agent.run()
