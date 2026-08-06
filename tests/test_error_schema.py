"""Unit tests for QA error and output schemas in FORGE AI QA & DevOps module."""

import pytest
from pydantic import ValidationError

from backend.schemas.qa_schema import QAError, QAOutput, QAErrorDetail
from backend.services.error_mapper import ErrorMapper, map_exception_to_qa_error


def test_qa_error_model_valid():
    """Validate QAError model instantiation with valid parameters."""
    error = QAError(
        id="QA-001",
        type="ImportError",
        severity="HIGH",
        component="backend",
        agent="BackendAgent",
        message="Module not found",
        suggestion="Install dependency"
    )

    assert error.id == "QA-001"
    assert error.type == "ImportError"
    assert error.severity == "HIGH"
    assert error.component == "backend"
    assert error.agent == "BackendAgent"
    assert error.message == "Module not found"
    assert error.suggestion == "Install dependency"

    # Backward compatibility properties
    assert error.error_type == "ImportError"
    assert error.affected_component == "backend"
    assert error.suggested_fix == "Install dependency"


def test_qa_error_model_missing_required_fields():
    """Validate QAError raises ValidationError when required fields are missing."""
    with pytest.raises(ValidationError):
        QAError(id="QA-001", type="SyntaxError")  # Missing required fields like severity, component, agent, message


def test_error_mapper_formatting_example():
    """Validate ErrorMapper produces the exact structure specified in task requirements."""
    err = ImportError("Module not found")
    qa_error = map_exception_to_qa_error(
        err,
        error_id="QA-001",
        suggestion="Install dependency"
    )

    dump = qa_error.model_dump()
    assert dump == {
        "id": "QA-001",
        "type": "ImportError",
        "severity": "HIGH",
        "component": "backend",
        "agent": "BackendAgent",
        "message": "Module not found",
        "suggestion": "Install dependency",
        "test_name": None,
    }


def test_qa_output_model_valid():
    """Validate QAOutput model instantiation with errors and metrics."""
    err1 = QAError(
        id="QA-001",
        type="SyntaxError",
        severity="CRITICAL",
        component="backend",
        agent="BackendAgent",
        message="Syntax error at line 10",
        suggestion="Fix syntax error"
    )
    err2 = QAError(
        id="QA-002",
        type="ConfigurationError",
        severity="MEDIUM",
        component="pm",
        agent="PMAgent",
        message="Missing env setting",
        suggestion="Add key to .env"
    )

    output = QAOutput(
        status="failed",
        tests_run=14,
        tests_passed=12,
        tests_failed=2,
        errors=[err1, err2],
        critical_errors=1,
        warnings=1,
        score=85.71,
        deployment_ready=False,
        next_step="Resolve 2 error(s) before deployment."
    )

    assert output.status == "failed"
    assert output.tests_run == 14
    assert output.tests_passed == 12
    assert output.tests_failed == 2
    assert len(output.errors) == 2
    assert output.critical_errors == 1
    assert output.warnings == 1
    assert output.score == 85.71
    assert output.deployment_ready is False
    assert output.next_step == "Resolve 2 error(s) before deployment."


def test_qa_error_detail_backward_compatibility():
    """Validate QAErrorDetail backward compatibility with legacy fields."""
    legacy_detail = QAErrorDetail(
        test_name="test_syntax_main.py",
        error_type="SyntaxError",
        message="Invalid syntax",
        affected_component="backend",
        suggested_fix="Fix typo"
    )

    assert legacy_detail.type == "SyntaxError"
    assert legacy_detail.component == "backend"
    assert legacy_detail.suggestion == "Fix typo"
    assert legacy_detail.error_type == "SyntaxError"
    assert legacy_detail.affected_component == "backend"
    assert legacy_detail.suggested_fix == "Fix typo"
