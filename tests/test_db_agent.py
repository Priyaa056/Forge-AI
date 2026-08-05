"""Unit tests for DBAgent."""

import json
import pytest
from pathlib import Path

from backend.agents.backend_agent import BackendAgent
from backend.agents.db_agent import DBAgent
from backend.schemas.db_schema import DBOutput
from backend.exceptions import MissingInputError, ValidationError


def test_db_agent_missing_input(tmp_path):
    agent = DBAgent(
        pm_output_path=str(tmp_path / "missing_pm.json"),
        backend_output_path=str(tmp_path / "missing_backend.json"),
        output_filepath=str(tmp_path / "db_output.json")
    )
    with pytest.raises(MissingInputError):
        agent.run()


def test_db_agent_execution(tmp_path):
    pm_file = tmp_path / "pm_output.json"
    pm_data = {
        "project_name": "TestApp",
        "description": "Test App",
        "features": ["Feature 1"],
        "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
        "database_entities": [
            {
                "name": "User",
                "fields": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "email", "type": "VARCHAR"}
                ]
            },
            {
                "name": "Post",
                "fields": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "user_id", "type": "INTEGER"},
                    {"name": "content", "type": "TEXT"}
                ]
            }
        ]
    }
    pm_file.write_text(json.dumps(pm_data), encoding="utf-8")

    backend_file = tmp_path / "backend_output.json"
    backend_agent = BackendAgent(pm_output_path=str(pm_file), output_filepath=str(backend_file))
    backend_agent.run()

    db_out = tmp_path / "db_output.json"
    db_agent = DBAgent(
        pm_output_path=str(pm_file),
        backend_output_path=str(backend_file),
        output_filepath=str(db_out)
    )

    output = db_agent.run()

    assert isinstance(output, DBOutput)
    assert output.database_system == "PostgreSQL"
    assert len(output.tables) == 2
    assert "class User(" in output.sqlalchemy_models_code
    assert "class Post(" in output.sqlalchemy_models_code
    assert output.alembic_metadata.revision_id is not None
    assert db_out.is_file()
