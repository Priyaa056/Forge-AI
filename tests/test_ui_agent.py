"""Unit and integration tests for FORGE AI UIAgent."""

import json
import pytest
from pathlib import Path

from backend.agents.ui_agent import UIAgent
from backend.schemas.ui_schema import UIOutput
from backend.exceptions import MissingInputError, ValidationError, GenerationError


@pytest.fixture
def sample_pm_specs():
    """Provides sample PM specs for Task Management, Blog, and E-commerce applications."""
    return {
        "task_management": {
            "project_name": "TaskFlow",
            "description": "Streamlined task management application for tracking daily work",
            "features": ["User registration & login", "CRUD tasks", "Filter tasks by priority", "Categories"],
            "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "SQLite"},
            "database_entities": [
                {
                    "name": "User",
                    "fields": [
                        {"name": "id", "type": "INTEGER"},
                        {"name": "email", "type": "VARCHAR"},
                        {"name": "hashed_password", "type": "VARCHAR"}
                    ]
                },
                {
                    "name": "Task",
                    "fields": [
                        {"name": "id", "type": "INTEGER"},
                        {"name": "title", "type": "VARCHAR"},
                        {"name": "description", "type": "TEXT"},
                        {"name": "status", "type": "VARCHAR"},
                        {"name": "priority", "type": "VARCHAR"},
                        {"name": "due_date", "type": "DATETIME"}
                    ]
                },
                {
                    "name": "Category",
                    "fields": [
                        {"name": "id", "type": "INTEGER"},
                        {"name": "name", "type": "VARCHAR"},
                        {"name": "color_code", "type": "VARCHAR"}
                    ]
                }
            ]
        },
        "blog_app": {
            "project_name": "DevBlog",
            "description": "Developer blogging platform for articles and community discussions",
            "features": ["User authentication", "Publish posts", "Comment system", "Tags & Categories"],
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
                    "name": "Post",
                    "fields": [
                        {"name": "id", "type": "INTEGER"},
                        {"name": "title", "type": "VARCHAR"},
                        {"name": "content", "type": "TEXT"},
                        {"name": "slug", "type": "VARCHAR"}
                    ]
                },
                {
                    "name": "Comment",
                    "fields": [
                        {"name": "id", "type": "INTEGER"},
                        {"name": "post_id", "type": "INTEGER"},
                        {"name": "content", "type": "TEXT"}
                    ]
                }
            ]
        },
        "ecommerce_app": {
            "project_name": "StoreFront",
            "description": "E-commerce store for browsing products, managing cart, and placing orders",
            "features": ["User accounts", "Product catalog", "Shopping cart", "Order checkout"],
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
                    "name": "Product",
                    "fields": [
                        {"name": "id", "type": "INTEGER"},
                        {"name": "name", "type": "VARCHAR"},
                        {"name": "price", "type": "FLOAT"},
                        {"name": "stock_quantity", "type": "INTEGER"}
                    ]
                },
                {
                    "name": "Order",
                    "fields": [
                        {"name": "id", "type": "INTEGER"},
                        {"name": "total_amount", "type": "FLOAT"},
                        {"name": "status", "type": "VARCHAR"}
                    ]
                }
            ]
        }
    }


def test_ui_agent_missing_input_file(tmp_path):
    """Test exception raised when PM input file does not exist."""
    agent = UIAgent(
        pm_output_path=str(tmp_path / "non_existent_pm.json"),
        output_filepath=str(tmp_path / "ui_output.json")
    )
    with pytest.raises(MissingInputError):
        agent.run()


def test_ui_agent_invalid_json(tmp_path):
    """Test exception raised when PM input contains malformed JSON."""
    bad_file = tmp_path / "bad_pm.json"
    bad_file.write_text("{ invalid json structure", encoding="utf-8")

    agent = UIAgent(
        pm_output_path=str(bad_file),
        output_filepath=str(tmp_path / "ui_output.json")
    )
    with pytest.raises(ValidationError):
        agent.run()


def test_ui_agent_missing_fields(tmp_path):
    """Test exception raised when PM input lacks mandatory schema fields."""
    incomplete_file = tmp_path / "incomplete_pm.json"
    incomplete_file.write_text(json.dumps({"description": "Missing project_name"}), encoding="utf-8")

    agent = UIAgent(
        pm_output_path=str(incomplete_file),
        output_filepath=str(tmp_path / "ui_output.json")
    )
    with pytest.raises(ValidationError):
        agent.run()


def test_ui_agent_empty_input(tmp_path):
    """Test exception raised when PM input file is empty."""
    empty_file = tmp_path / "empty_pm.json"
    empty_file.write_text("", encoding="utf-8")

    agent = UIAgent(
        pm_output_path=str(empty_file),
        output_filepath=str(tmp_path / "ui_output.json")
    )
    with pytest.raises(ValidationError):
        agent.run()






