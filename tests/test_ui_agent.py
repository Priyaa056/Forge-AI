"""Unit tests for UIAgent."""

import json
import pytest

from backend.agents.ui_agent import UIAgent
from backend.schemas.ui_schema import UIOutput
from backend.exceptions import MissingInputError, ValidationError


def test_ui_agent_missing_input(tmp_path):
    agent = UIAgent(
        pm_output_path=str(tmp_path / "missing_pm.json"),
        output_filepath=str(tmp_path / "ui_output.json")
    )
    with pytest.raises(MissingInputError):
        agent.run()


def test_ui_agent_execution(tmp_path):
    pm_file = tmp_path / "pm_output.json"
    pm_data = {
        "project_name": "TaskFlow",
        "description": "Task management application",
        "features": ["User authentication", "Task CRUD"],
        "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
        "database_entities": [
            {
                "name": "Task",
                "fields": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "title", "type": "VARCHAR"},
                    {"name": "status", "type": "VARCHAR"}
                ]
            }
        ]
    }
    pm_file.write_text(json.dumps(pm_data), encoding="utf-8")

    ui_file = tmp_path / "ui_output.json"
    agent = UIAgent(
        pm_output_path=str(pm_file),
        output_filepath=str(ui_file)
    )

    output = agent.run()

    assert isinstance(output, UIOutput)
    assert output.project_name == "TaskFlow"
    assert output.framework == "React"
    assert len(output.pages) >= 3
    assert len(output.components) >= 4
    assert len(output.routes) >= 3
    assert "src/pages/Dashboard.jsx" in output.code_files
    assert ui_file.is_file()
