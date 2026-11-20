"""Unit tests for SelfHealingManager foundation service and repair attempt limit enforcement."""

import pytest
from backend.services.self_healing import SelfHealingManager, MAX_REPAIR_ATTEMPTS, SelfHealingResult, RepairRequest


def test_self_healing_passed_qa():
    """Verify SelfHealingManager recommendation when QA passes."""
    manager = SelfHealingManager()
    qa_data = {
        "status": "passed",
        "tests_run": 10,
        "tests_passed": 10,
        "tests_failed": 0,
        "errors": [],
        "deployment_ready": True,
        "fix_required": False
    }

    result = manager.evaluate(qa_data)

    assert result.action == "proceed_to_deploy"
    assert result.attempt_count == 0
    assert result.repair_request is None
    assert "Application is ready for deployment" in result.message


def test_self_healing_repair_request_creation():
    """Verify repair request generation and responsible agent mapping on QA failure."""
    manager = SelfHealingManager()
    qa_data = {
        "status": "failed",
        "tests_run": 10,
        "tests_passed": 8,
        "tests_failed": 2,
        "errors": [
            {
                "id": "QA-001",
                "type": "SyntaxError",
                "severity": "CRITICAL",
                "component": "backend",
                "agent": "BackendAgent",
                "message": "Syntax error in backend/main.py",
                "suggestion": "Fix line 5"
            }
        ],
        "affected_component": "backend",
        "deployment_ready": False,
        "fix_required": True
    }

    result = manager.evaluate(qa_data)

    assert result.action == "request_repair"
    assert result.attempt_count == 1
    assert result.repair_request is not None
    assert isinstance(result.repair_request, RepairRequest)
    assert result.repair_request.attempt_number == 1
    assert result.repair_request.max_attempts == MAX_REPAIR_ATTEMPTS
    assert result.repair_request.responsible_agent == "BackendAgent"
    assert result.repair_request.affected_component == "backend"


def test_self_healing_max_repair_attempts_exceeded():
    """Verify MAX_REPAIR_ATTEMPTS = 3 enforcement and stopping condition."""
    manager = SelfHealingManager(max_attempts=3)
    failing_qa_data = {
        "status": "failed",
        "tests_run": 10,
        "tests_passed": 9,
        "tests_failed": 1,
        "errors": [
            {
                "id": "QA-001",
                "type": "DatabaseError",
                "severity": "CRITICAL",
                "component": "database",
                "agent": "DBAgent",
                "message": "Connection refused",
                "suggestion": "Check db"
            }
        ],
        "affected_component": "database",
        "deployment_ready": False,
        "fix_required": True
    }

    # Attempt 1
    res1 = manager.evaluate(failing_qa_data)
    assert res1.action == "request_repair"
    assert res1.attempt_count == 1

    # Attempt 2
    res2 = manager.evaluate(failing_qa_data)
    assert res2.action == "request_repair"
    assert res2.attempt_count == 2

    # Attempt 3
    res3 = manager.evaluate(failing_qa_data)
    assert res3.action == "request_repair"
    assert res3.attempt_count == 3

    # Attempt 4 (Exceeds limit)
    res4 = manager.evaluate(failing_qa_data)
    assert res4.action == "max_attempts_exceeded"
    assert res4.attempt_count == 4
    assert res4.repair_request is None
    assert "Maximum repair attempts (3) reached" in res4.message


def test_self_healing_reset():
    """Verify SelfHealingManager reset resets counter and history."""
    manager = SelfHealingManager()
    failing_qa_data = {"status": "failed", "tests_failed": 1, "deployment_ready": False}
    manager.evaluate(failing_qa_data)
    assert manager.attempt_count == 1

    manager.reset()
    assert manager.attempt_count == 0
    assert len(manager.history) == 0
