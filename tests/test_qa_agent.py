"""Unit tests for QA Agent inspection, failure classification, and self-healing output schema."""

import os
import json
import pytest
from pathlib import Path

from backend.agents.qa_agent import QAAgent
from backend.schemas.qa_schema import QAOutput, QAErrorDetail


def test_qa_agent_execution_success(tmp_path):
    """Test QA Agent execution on valid project structure."""
    qa_output_path = tmp_path / "qa_output.json"
    agent = QAAgent(
        project_root=str(Path(".").resolve()),
        output_filepath=str(qa_output_path)
    )
    result = agent.run()
    
    assert isinstance(result, QAOutput)
    assert result.status in ["passed", "failed"]
    assert result.tests_run >= 10
    assert qa_output_path.is_file()


def test_qa_agent_syntax_error_detection(tmp_path):
    """Test QA Agent detection and classification of Python syntax errors."""
    project_dir = tmp_path / "mock_project"
    backend_dir = project_dir / "backend"
    backend_dir.mkdir(parents=True)
    
    # Write python file with deliberate syntax error
    invalid_py = backend_dir / "invalid.py"
    invalid_py.write_text("def broken_func(: return True", encoding="utf-8")
    
    qa_output_path = project_dir / "outputs" / "qa_output.json"
    agent = QAAgent(
        project_root=str(project_dir),
        output_filepath=str(qa_output_path)
    )
    result = agent.run()
    
    assert result.status == "failed"
    assert result.fix_required is True
    assert result.tests_failed > 0
    assert any(err.error_type == "SyntaxError" for err in result.errors)
    assert result.affected_component == "backend"


def test_qa_agent_frontend_build_check(tmp_path):
    """Test QA Agent detection of missing build script in frontend package.json."""
    project_dir = tmp_path / "mock_frontend_proj"
    frontend_dir = project_dir / "frontend"
    frontend_dir.mkdir(parents=True)
    
    pkg_json = frontend_dir / "package.json"
    pkg_json.write_text(json.dumps({"name": "mock-frontend", "version": "1.0.0"}), encoding="utf-8")
    
    agent = QAAgent(
        project_root=str(project_dir),
        output_filepath=str(project_dir / "qa_output.json")
    )
    errors = agent.check_frontend_build()
    
    assert len(errors) == 1
    assert errors[0].error_type == "FrontendBuildError"
    assert errors[0].affected_component == "frontend"


def test_qa_agent_secret_leak_detection(tmp_path):
    """Test QA Agent detection of potential hardcoded secret keys in specs."""
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir()
    pm_file = outputs_dir / "pm_output.json"
    pm_file.write_text(json.dumps({"secret": "AIzaSyFakeGoogleApiKey12345"}), encoding="utf-8")

    agent = QAAgent(
        project_root=str(tmp_path),
        pm_output_path=str(pm_file),
        output_filepath=str(outputs_dir / "qa_output.json")
    )
    agent.load_inputs()
    errors = agent.check_configuration_errors()
    
    assert len(errors) > 0
    assert errors[0].error_type == "ConfigurationError"
    assert errors[0].affected_component == "auth"
