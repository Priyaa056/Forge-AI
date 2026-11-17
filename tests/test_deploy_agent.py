"""Unit tests for Deploy Agent packaging, configuration, deployment status, and health checks."""

import os
import json
import pytest
from pathlib import Path

from backend.agents.deploy_agent import DeployAgent
from backend.schemas.deploy_schema import DeployOutput, HealthCheckResult


def test_deploy_agent_execution_success(tmp_path):
    """Test Deploy Agent lifecycle with passing QA status."""
    qa_path = tmp_path / "qa_output.json"
    qa_path.write_text(json.dumps({
        "status": "passed",
        "tests_run": 10,
        "tests_passed": 10,
        "tests_failed": 0,
        "errors": [],
        "affected_component": None,
        "fix_required": False
    }), encoding="utf-8")

    pm_path = tmp_path / "pm_output.json"
    pm_path.write_text(json.dumps({
        "project_name": "TaskFlow",
        "description": "Task app"
    }), encoding="utf-8")

    deploy_path = tmp_path / "deploy_output.json"
    agent = DeployAgent(
        qa_output_path=str(qa_path),
        pm_output_path=str(pm_path),
        output_filepath=str(deploy_path)
    )
    result = agent.run()

    assert isinstance(result, DeployOutput)
    assert result.status == "success"
    assert result.live_url is not None
    assert result.docker_config is not None
    assert result.docker_config.backend_image == "taskflow-backend:latest"
    assert len(result.health_checks) > 0
    assert deploy_path.is_file()


def test_deploy_agent_aborts_on_qa_failure(tmp_path):
    """Test Deploy Agent aborts deployment when QA reports failures."""
    qa_path = tmp_path / "qa_output.json"
    qa_path.write_text(json.dumps({
        "status": "failed",
        "tests_run": 10,
        "tests_passed": 8,
        "tests_failed": 2,
        "errors": [{"test_name": "test_syntax", "error_type": "SyntaxError", "message": "Syntax error", "affected_component": "backend"}],
        "affected_component": "backend",
        "fix_required": True
    }), encoding="utf-8")

    deploy_path = tmp_path / "deploy_output.json"
    agent = DeployAgent(
        qa_output_path=str(qa_path),
        output_filepath=str(deploy_path)
    )
    result = agent.run()

    assert result.status == "failed"
    assert result.live_url is None
    assert result.affected_component == "backend"
    assert "Deployment aborted: QA Agent reported test failures." in result.logs


def test_deploy_agent_docker_config_spec(tmp_path):
    """Test Deploy Agent generation of correct Docker packaging specifications."""
    agent = DeployAgent(output_filepath=str(tmp_path / "deploy_output.json"))
    result = agent.run()

    assert result.docker_config is not None
    assert result.docker_config.compose_file == "docker-compose.yml"
    assert result.docker_config.exposed_ports["backend"] == 8000
    assert result.docker_config.exposed_ports["frontend"] == 3000
    assert result.docker_config.exposed_ports["postgres"] == 5432


def test_deploy_agent_truthful_health_check_unreachable():
    """Test run_health_checks reports status 'unhealthy' when endpoint is unreachable."""
    agent = DeployAgent()
    results = agent.run_health_checks("http://127.0.0.1:59999")  # Unused port

    assert len(results) == 2
    for hc in results:
        assert hc.status == "unhealthy"
        assert hc.status_code in [0, 500, 502, 503, 504]
        assert "unreachable" in hc.message.lower() or "error" in hc.message.lower() or "refused" in hc.message.lower()

