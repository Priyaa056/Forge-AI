"""Unit tests for AuthAgent."""

import json
import pytest

from backend.agents.backend_agent import BackendAgent
from backend.agents.db_agent import DBAgent
from backend.agents.auth_agent import AuthAgent
from backend.schemas.auth_schema import AuthOutput
from backend.exceptions import MissingInputError, ValidationError


def test_auth_agent_missing_input(tmp_path):
    agent = AuthAgent(
        pm_output_path=str(tmp_path / "missing_pm.json"),
        backend_output_path=str(tmp_path / "missing_backend.json"),
        db_output_path=str(tmp_path / "missing_db.json"),
        output_filepath=str(tmp_path / "auth_output.json")
    )
    with pytest.raises(MissingInputError):
        agent.run()


def _write_valid_pm(tmp_path) -> str:
    """Helper: write a minimal valid pm_output.json and return its path string."""
    pm_file = tmp_path / "pm_output.json"
    pm_file.write_text(json.dumps({
        "project_name": "TestApp",
        "description": "Test App",
        "features": ["Auth Feature"],
        "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
        "database_entities": [
            {
                "name": "User",
                "fields": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "email", "type": "VARCHAR"},
                    {"name": "hashed_password", "type": "VARCHAR"}
                ]
            }
        ]
    }), encoding="utf-8")
    return str(pm_file)


def test_auth_agent_invalid_backend_json(tmp_path):
    """AuthAgent must raise ValidationError when backend_output.json contains malformed JSON."""
    pm_path = _write_valid_pm(tmp_path)

    invalid_backend = tmp_path / "backend_output.json"
    invalid_backend.write_text("not valid json {{{", encoding="utf-8")

    agent = AuthAgent(
        pm_output_path=pm_path,
        backend_output_path=str(invalid_backend),
        db_output_path=str(tmp_path / "db_output.json"),
        output_filepath=str(tmp_path / "auth_output.json")
    )
    with pytest.raises(ValidationError):
        agent.run()




