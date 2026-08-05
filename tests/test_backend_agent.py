"""Unit tests for BackendAgent."""

import json
import pytest
from pathlib import Path

from backend.agents.backend_agent import BackendAgent
from backend.schemas.backend_schema import BackendOutput
from backend.exceptions import MissingInputError, ValidationError


def test_backend_agent_missing_input(tmp_path):
    agent = BackendAgent(
        pm_output_path=str(tmp_path / "non_existent.json"),
        output_filepath=str(tmp_path / "backend_output.json")
    )
    with pytest.raises(MissingInputError):
        agent.run()


def test_backend_agent_invalid_json(tmp_path):
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("not json content", encoding="utf-8")

    agent = BackendAgent(
        pm_output_path=str(invalid_file),
        output_filepath=str(tmp_path / "backend_output.json")
    )
    with pytest.raises(ValidationError):
        agent.run()


def test_backend_agent_execution(tmp_path):
    pm_file = tmp_path / "pm_output.json"
    pm_data = {
        "project_name": "TestApp",
        "description": "Test App Description",
        "features": ["Feature A"],
        "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
        "database_entities": [
            {
                "name": "User",
                "fields": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "username", "type": "VARCHAR"},
                    {"name": "email", "type": "VARCHAR"}
                ]
            },
            {
                "name": "Item",
                "fields": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "user_id", "type": "INTEGER"},
                    {"name": "title", "type": "VARCHAR"}
                ]
            }
        ]
    }
    pm_file.write_text(json.dumps(pm_data), encoding="utf-8")

    out_file = tmp_path / "backend_output.json"
    agent = BackendAgent(
        pm_output_path=str(pm_file),
        output_filepath=str(out_file)
    )

    output = agent.run()

    assert isinstance(output, BackendOutput)
    assert output.project_name == "TestApp"
    assert len(output.endpoints) > 0
    assert len(output.service_layer) == 2
    assert len(output.repository_layer) == 2
    assert out_file.is_file()
