"""Unit tests for DeployAgent."""

import json
import pytest

from backend.agents.deploy_agent import DeployAgent
from backend.schemas.deploy_schema import DeployOutput
from backend.exceptions import MissingInputError


def test_deploy_agent_missing_input(tmp_path):
    agent = DeployAgent(
        pm_output_path=str(tmp_path / "missing_pm.json"),
        output_filepath=str(tmp_path / "deploy_output.json")
    )
    with pytest.raises(MissingInputError):
        agent.run()


def test_deploy_agent_execution(tmp_path):
    pm_file = tmp_path / "pm_output.json"
    pm_data = {
        "project_name": "StoreFront",
        "description": "E-commerce platform",
        "features": ["Product catalog", "Orders"],
        "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
        "database_entities": [
            {
                "name": "Product",
                "fields": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "name", "type": "VARCHAR"}
                ]
            }
        ]
    }
    pm_file.write_text(json.dumps(pm_data), encoding="utf-8")

    deploy_file = tmp_path / "deploy_output.json"
    agent = DeployAgent(
        pm_output_path=str(pm_file),
        output_filepath=str(deploy_file)
    )

    output = agent.run()

    assert isinstance(output, DeployOutput)
    assert output.project_name == "StoreFront"
    assert output.deployment_target == "Docker"
    assert output.container_status == "SUCCESS"
    assert "FROM python" in output.dockerfile_content
    assert "services:" in output.docker_compose_content
    assert "DATABASE_URL" in output.environment_variables_configured
    assert output.health_check_status == "HEALTHY"
    assert len(output.deployment_logs) >= 3
    assert deploy_file.is_file()
