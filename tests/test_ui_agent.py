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


def test_ui_agent_valid_execution(tmp_path, sample_pm_specs):
    """Test valid execution of UIAgent using Task Management PM input."""
    pm_file = tmp_path / "pm_output.json"
    pm_file.write_text(json.dumps(sample_pm_specs["task_management"]), encoding="utf-8")

    out_file = tmp_path / "ui_output.json"
    agent = UIAgent(
        pm_output_path=str(pm_file),
        output_filepath=str(out_file)
    )

    output = agent.run()

    assert isinstance(output, UIOutput)
    assert output.project_name == "TaskFlow"
    assert len(output.pages) >= 3
    assert len(output.routes) >= 3
    assert len(output.components) >= 4
    assert len(output.forms) >= 2
    assert len(output.frontend_dependencies) >= 5
    assert len(output.api_requirements) >= 4
    assert output.styling_requirements.css_approach is not None
    assert out_file.is_file()


def test_ui_agent_multi_domain_specifications(tmp_path, sample_pm_specs):
    """Test UIAgent across Task Management, Blog, and E-commerce applications and verify specs differ."""
    generated_specs = {}

    for domain_key, pm_data in sample_pm_specs.items():
        pm_file = tmp_path / f"pm_{domain_key}.json"
        pm_file.write_text(json.dumps(pm_data), encoding="utf-8")

        out_file = tmp_path / f"ui_{domain_key}.json"
        agent = UIAgent(
            pm_output_path=str(pm_file),
            output_filepath=str(out_file)
        )
        spec = agent.run()
        generated_specs[domain_key] = spec

        # Verify domain-specific details
        assert spec.project_name == pm_data["project_name"]
        assert out_file.is_file()

    # Verify that different input prompts/domains produce distinct UI specifications
    task_spec = generated_specs["task_management"]
    blog_spec = generated_specs["blog_app"]
    ecom_spec = generated_specs["ecommerce_app"]

    # Projects have distinct names
    assert task_spec.project_name != blog_spec.project_name
    assert blog_spec.project_name != ecom_spec.project_name

    # Page names differ by domain entity
    task_page_names = [p.name for p in task_spec.pages]
    blog_page_names = [p.name for p in blog_spec.pages]
    ecom_page_names = [p.name for p in ecom_spec.pages]

    assert "TaskPage" in task_page_names
    assert "PostPage" in blog_page_names
    assert "ProductPage" in ecom_page_names

    # Form entities differ by domain
    task_form_entities = [f.entity_name for f in task_spec.forms]
    blog_form_entities = [f.entity_name for f in blog_spec.forms]
    ecom_form_entities = [f.entity_name for f in ecom_spec.forms]

    assert "Task" in task_form_entities
    assert "Post" in blog_form_entities
    assert "Product" in ecom_form_entities


def test_ui_agent_fallback_on_api_failure(tmp_path, sample_pm_specs, monkeypatch):
    """Test fallback mechanism when Gemini LLM raises an API failure."""
    pm_file = tmp_path / "pm_output.json"
    pm_file.write_text(json.dumps(sample_pm_specs["task_management"]), encoding="utf-8")

    out_file = tmp_path / "ui_output.json"
    agent = UIAgent(
        pm_output_path=str(pm_file),
        output_filepath=str(out_file)
    )

    # Mock get_gemini_model to return a model that raises an exception on generate_content
    class MockFailingModel:
        def generate_content(self, prompt):
            raise RuntimeError("Simulated Gemini API Network/Rate Limit Failure")

    monkeypatch.setattr(agent, "get_gemini_model", lambda: MockFailingModel())

    # Execution should not crash; it logs a warning and successfully falls back to rule-based generation
    output = agent.run()
    assert isinstance(output, UIOutput)
    assert output.project_name == "TaskFlow"
    assert out_file.is_file()
