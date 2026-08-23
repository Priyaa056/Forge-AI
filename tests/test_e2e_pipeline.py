"""End-to-end Integration tests for FORGE AI Backend, DB, and Auth Agents across multiple domain applications."""

import json
import pytest
from pathlib import Path

from backend.agents.backend_agent import BackendAgent
from backend.agents.db_agent import DBAgent
from backend.agents.auth_agent import AuthAgent
from backend.agents.ui_agent import UIAgent
from backend.schemas.backend_schema import BackendOutput
from backend.schemas.db_schema import DBOutput
from backend.schemas.auth_schema import AuthOutput
from backend.schemas.ui_schema import UIOutput


@pytest.fixture
def sample_domains():
    """Provides sample PM specs for Task Management, Blog, and E-commerce domains."""
    return {
        "Task Management": {
            "project_name": "TaskFlow",
            "description": "Streamlined task management application",
            "features": ["User registration", "CRUD tasks", "Task priorities", "Categories"],
            "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
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
                        {"name": "user_id", "type": "INTEGER"},
                        {"name": "title", "type": "VARCHAR"},
                        {"name": "description", "type": "TEXT"},
                        {"name": "status", "type": "VARCHAR"}
                    ]
                },
                {
                    "name": "Category",
                    "fields": [
                        {"name": "id", "type": "INTEGER"},
                        {"name": "name", "type": "VARCHAR"}
                    ]
                }
            ]
        },
        "Blog Application": {
            "project_name": "DevBlog",
            "description": "Developer publishing and blogging platform",
            "features": ["Publish articles", "Comments", "Tags and Categories", "Author profiles"],
            "tech_stack": {"frontend": "Next.js", "backend": "FastAPI", "database": "PostgreSQL"},
            "database_entities": [
                {
                    "name": "User",
                    "fields": [
                        {"name": "id", "type": "INTEGER"},
                        {"name": "username", "type": "VARCHAR"},
                        {"name": "email", "type": "VARCHAR"},
                        {"name": "hashed_password", "type": "VARCHAR"}
                    ]
                },
                {
                    "name": "Post",
                    "fields": [
                        {"name": "id", "type": "INTEGER"},
                        {"name": "user_id", "type": "INTEGER"},
                        {"name": "title", "type": "VARCHAR"},
                        {"name": "slug", "type": "VARCHAR"},
                        {"name": "content", "type": "TEXT"}
                    ]
                },
                {
                    "name": "Comment",
                    "fields": [
                        {"name": "id", "type": "INTEGER"},
                        {"name": "post_id", "type": "INTEGER"},
                        {"name": "user_id", "type": "INTEGER"},
                        {"name": "content", "type": "TEXT"}
                    ]
                }
            ]
        },
        "E-commerce Platform": {
            "project_name": "StoreFront",
            "description": "Online e-commerce shopping platform",
            "features": ["Product catalog", "Shopping cart", "Order processing", "User accounts"],
            "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
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
                        {"name": "user_id", "type": "INTEGER"},
                        {"name": "total_amount", "type": "FLOAT"},
                        {"name": "status", "type": "VARCHAR"}
                    ]
                }
            ]
        }
    }


def test_e2e_pipeline_all_domains(tmp_path, sample_domains):
    """Test full PM -> Backend -> DB -> Auth -> UI pipeline for Task Management, Blog, and E-commerce domains."""
    for domain_name, pm_data in sample_domains.items():
        domain_dir = tmp_path / domain_name.replace(" ", "_").lower()
        domain_dir.mkdir()

        pm_path = domain_dir / "pm_output.json"
        backend_path = domain_dir / "backend_output.json"
        db_path = domain_dir / "db_output.json"
        auth_path = domain_dir / "auth_output.json"
        ui_path = domain_dir / "ui_output.json"

        # 1. Write PM Output
        pm_path.write_text(json.dumps(pm_data), encoding="utf-8")

        # 2. Run Backend Agent
        backend_agent = BackendAgent(pm_output_path=str(pm_path), output_filepath=str(backend_path))
        backend_out = backend_agent.run()
        assert isinstance(backend_out, BackendOutput)
        assert backend_out.project_name == pm_data["project_name"]
        assert len(backend_out.endpoints) >= len(pm_data["database_entities"]) * 4

        # 3. Run Database Agent
        db_agent = DBAgent(pm_output_path=str(pm_path), backend_output_path=str(backend_path), output_filepath=str(db_path))
        db_out = db_agent.run()
        assert isinstance(db_out, DBOutput)
        assert db_out.project_name == pm_data["project_name"]
        assert len(db_out.tables) == len(pm_data["database_entities"])
        assert "Base = declarative_base()" in db_out.sqlalchemy_models_code

        # 4. Run Auth Agent
        auth_agent = AuthAgent(
            pm_output_path=str(pm_path),
            backend_output_path=str(backend_path),
            db_output_path=str(db_path),
            output_filepath=str(auth_path)
        )
        auth_out = auth_agent.run()
        assert isinstance(auth_out, AuthOutput)
        assert auth_out.project_name == pm_data["project_name"]
        assert auth_out.password_security.hashing_algorithm == "bcrypt"
        assert auth_out.jwt_strategy.algorithm == "HS256"

        # 5. Run UI Agent
        ui_agent = UIAgent(
            pm_output_path=str(pm_path),
            output_filepath=str(ui_path)
        )
        ui_out = ui_agent.run()
        assert isinstance(ui_out, UIOutput)
        assert ui_out.project_name == pm_data["project_name"]
        assert len(ui_out.pages) >= 3

        # Check file persistence
        assert backend_path.is_file()
        assert db_path.is_file()
        assert auth_path.is_file()
        assert ui_path.is_file()

