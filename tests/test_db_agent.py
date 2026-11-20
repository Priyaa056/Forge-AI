"""Unit tests for DBAgent."""

import json
import pytest
from pathlib import Path

from backend.agents.backend_agent import BackendAgent
from backend.agents.db_agent import DBAgent
from backend.schemas.db_schema import DBOutput
from backend.exceptions import MissingInputError, ValidationError
import json


def test_db_agent_missing_input(tmp_path):
    agent = DBAgent(
        pm_output_path=str(tmp_path / "missing_pm.json"),
        backend_output_path=str(tmp_path / "missing_backend.json"),
        output_filepath=str(tmp_path / "db_output.json")
    )
    with pytest.raises(MissingInputError):
        agent.run()


def test_db_agent_invalid_pm_json(tmp_path):
    """DBAgent must raise ValidationError when pm_output.json contains malformed JSON."""
    invalid_pm = tmp_path / "invalid_pm.json"
    invalid_pm.write_text("not valid json {{{", encoding="utf-8")

    agent = DBAgent(
        pm_output_path=str(invalid_pm),
        backend_output_path=str(tmp_path / "backend_output.json"),
        output_filepath=str(tmp_path / "db_output.json")
    )
    with pytest.raises(ValidationError):
        agent.run()


def test_db_agent_invalid_backend_json(tmp_path):
    """DBAgent must raise ValidationError when backend_output.json contains malformed JSON."""
    # Valid PM file
    pm_file = tmp_path / "pm_output.json"
    pm_file.write_text(json.dumps({
        "project_name": "TestApp",
        "description": "Test",
        "features": ["Feature 1"],
        "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
        "database_entities": [
            {"name": "User", "fields": [{"name": "id", "type": "INTEGER"}]}
        ]
    }), encoding="utf-8")

    # Malformed backend file
    invalid_backend = tmp_path / "backend_output.json"
    invalid_backend.write_text("not valid json {{{", encoding="utf-8")

    agent = DBAgent(
        pm_output_path=str(pm_file),
        backend_output_path=str(invalid_backend),
        output_filepath=str(tmp_path / "db_output.json")
    )
    with pytest.raises(ValidationError):
        agent.run()








