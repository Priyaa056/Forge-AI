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
    assert output.alembic_metadata.revision_id != "0001_initial_schema"
    assert db_out.is_file()


def test_db_agent_check_constraint_generation(tmp_path):
    """DBAgent should generate CHECK constraints for fields that logically require value validation."""
    pm_file = tmp_path / "pm_output.json"
    pm_data = {
        "project_name": "StoreApp",
        "description": "E-commerce store",
        "features": ["Products", "Reviews"],
        "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
        "database_entities": [
            {
                "name": "Product",
                "fields": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "name", "type": "VARCHAR"},
                    {"name": "price", "type": "DECIMAL"},
                    {"name": "stock_quantity", "type": "INTEGER"}
                ]
            },
            {
                "name": "Review",
                "fields": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "rating", "type": "INTEGER"},
                    {"name": "comment", "type": "TEXT"}
                ]
            }
        ]
    }
    pm_file.write_text(json.dumps(pm_data), encoding="utf-8")

    backend_file = tmp_path / "backend_output.json"
    BackendAgent(pm_output_path=str(pm_file), output_filepath=str(backend_file)).run()

    db_out = tmp_path / "db_output.json"
    db_agent = DBAgent(pm_output_path=str(pm_file), backend_output_path=str(backend_file), output_filepath=str(db_out))
    output = db_agent.run()

    product_table = next(t for t in output.tables if t.model_name == "Product")
    price_col = next(c for c in product_table.columns if c.name == "price")
    stock_col = next(c for c in product_table.columns if c.name == "stock_quantity")

    assert price_col.check_constraint == "price >= 0"
    assert stock_col.check_constraint == "stock_quantity >= 0"

    review_table = next(t for t in output.tables if t.model_name == "Review")
    rating_col = next(c for c in review_table.columns if c.name == "rating")
    assert rating_col.check_constraint == "rating >= 1 AND rating <= 5"

    assert "CheckConstraint('price >= 0')" in output.sqlalchemy_models_code
    assert "CheckConstraint('rating >= 1 AND rating <= 5')" in output.sqlalchemy_models_code


def test_db_agent_no_check_constraint_when_not_needed(tmp_path):
    """DBAgent should keep check_constraint as None when no CHECK constraint is required."""
    pm_file = tmp_path / "pm_output.json"
    pm_data = {
        "project_name": "SimpleApp",
        "description": "Simple app",
        "features": ["User management"],
        "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
        "database_entities": [
            {
                "name": "User",
                "fields": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "username", "type": "VARCHAR"},
                    {"name": "email", "type": "VARCHAR"}
                ]
            }
        ]
    }
    pm_file.write_text(json.dumps(pm_data), encoding="utf-8")

    backend_file = tmp_path / "backend_output.json"
    BackendAgent(pm_output_path=str(pm_file), output_filepath=str(backend_file)).run()

    db_out = tmp_path / "db_output.json"
    db_agent = DBAgent(pm_output_path=str(pm_file), backend_output_path=str(backend_file), output_filepath=str(db_out))
    output = db_agent.run()

    user_table = next(t for t in output.tables if t.model_name == "User")
    for col in user_table.columns:
        assert col.check_constraint is None


def test_db_agent_dynamic_migration_revision_id(tmp_path):
    """Migration metadata revision_id must be dynamic, non-hardcoded, and unique across projects."""
    rev_id1 = DBAgent.generate_revision_id("ProjectAlpha", 1)
    rev_id2 = DBAgent.generate_revision_id("ProjectBeta", 1)

    assert rev_id1 != "0001_initial_schema"
    assert rev_id2 != "0001_initial_schema"
    assert rev_id1 != rev_id2
    assert rev_id1.startswith("rev_0001_projectalpha_")
    assert rev_id2.startswith("rev_0001_projectbeta_")
