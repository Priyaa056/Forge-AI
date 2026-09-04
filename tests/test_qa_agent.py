"""Unit tests for QAAgent."""

import json
import pytest

from backend.agents.qa_agent import QAAgent
from backend.schemas.qa_schema import QAOutput
from backend.exceptions import MissingInputError


def test_qa_agent_missing_input(tmp_path):
    agent = QAAgent(
        pm_output_path=str(tmp_path / "missing_pm.json"),
        output_filepath=str(tmp_path / "qa_output.json")
    )
    with pytest.raises(MissingInputError):
        agent.run()


def test_qa_agent_execution(tmp_path):
    pm_file = tmp_path / "pm_output.json"
    pm_data = {
        "project_name": "DevBlog",
        "description": "Blogging platform",
        "features": ["Publish posts", "Comments"],
        "tech_stack": {"frontend": "Next.js", "backend": "FastAPI", "database": "PostgreSQL"},
        "database_entities": [
            {
                "name": "Post",
                "fields": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "title", "type": "VARCHAR"}
                ]
            }
        ]
    }
    pm_file.write_text(json.dumps(pm_data), encoding="utf-8")

    qa_file = tmp_path / "qa_output.json"
    agent = QAAgent(
        pm_output_path=str(pm_file),
        output_filepath=str(qa_file)
    )

    output = agent.run()

    assert isinstance(output, QAOutput)
    assert output.project_name == "DevBlog"
    assert output.total_tests > 0
    assert output.passed_tests == output.total_tests
    assert output.failed_tests == 0
    assert output.coverage_percentage >= 90.0
    assert len(output.test_suites) >= 4
    assert output.lint_status == "PASSED"
    assert output.security_scan_status == "PASSED"
    assert "tests/test_generated_api.py" in output.test_code_files
    assert qa_file.is_file()
