"""Unit tests for QA Agent inspection, failure classification, and self-healing output schema."""

import os
import json
import pytest
from pathlib import Path

from backend.agents.qa_agent import QAAgent
from backend.schemas.qa_schema import QAOutput, QAErrorDetail










def test_qa_summary_generation(tmp_path):
    """Test generate_qa_summary formatting and output file generation."""
    from backend.services.qa_summary import generate_qa_summary

    summary_file = tmp_path / "qa_summary.txt"
    qa_data = {
        "status": "passed",
        "tests_run": 10,
        "tests_passed": 10,
        "tests_failed": 0,
        "critical_errors": 0,
        "warnings": 0,
        "deployment_ready": True
    }
    content = generate_qa_summary(qa_data, output_path=str(summary_file))

    assert summary_file.is_file()
    assert "Status : PASSED" in content
    assert "Tests Run : 10" in content
    assert "Deployment Ready : YES" in content

