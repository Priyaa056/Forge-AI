"""Unit tests for FailureClassifier service in FORGE AI QA & DevOps module."""

import pytest
import sqlite3
from backend.services.failure_classifier import FailureClassifier, FailureClassification


def test_classify_import_error():
    """Verify ImportError detection, severity, and responsible agent mapping."""
    err = ImportError("No module named 'invalid_package'")
    res = FailureClassifier.classify(err)

    assert res.category == "ImportError"
    assert res.severity == "HIGH"
    assert res.agent in ["Backend Agent", "BackendAgent"]
    assert res.agent_class == "BackendAgent"
    assert res.component == "backend"


def test_classify_syntax_error():
    """Verify SyntaxError detection, severity, and responsible agent mapping."""
    err = SyntaxError("invalid syntax at line 5")
    res = FailureClassifier.classify(err)

    assert res.category == "SyntaxError"
    assert res.severity == "CRITICAL"
    assert res.agent in ["Backend Agent", "BackendAgent"]
    assert res.agent_class == "BackendAgent"
    assert res.component == "backend"


def test_classify_unknown_error():
    """Verify UnknownError fallback, severity, and responsible agent mapping."""
    err = RuntimeError("Unexpected internal crash")
    res = FailureClassifier.classify(err)

    assert res.category == "UnknownError"
    assert res.severity == "LOW"
    assert res.agent in ["QA Agent", "QAAgent"]
    assert res.agent_class == "QAAgent"
    assert res.component == "qa"


def test_all_supported_categories_agent_mapping():
    """Verify agent mappings across all supported error categories."""
    expected_mappings = {
        "ImportError": ("Backend Agent", "BackendAgent"),
        "SyntaxError": ("Backend Agent", "BackendAgent"),
        "DependencyError": ("Backend Agent", "BackendAgent"),
        "DatabaseError": ("DB Agent", "DBAgent"),
        "APIError": ("Backend Agent", "BackendAgent"),
        "BuildError": ("UI Agent", "UIAgent"),
        "ConfigurationError": ("PM Agent", "PMAgent"),
        "AuthenticationError": ("Auth Agent", "AuthAgent"),
        "IntegrationError": ("QA Agent", "QAAgent"),
        "DeploymentError": ("Deploy Agent", "DeployAgent"),
        "SecurityError": ("Auth Agent", "AuthAgent"),
        "UnknownError": ("QA Agent", "QAAgent"),
    }

    for category, (expected_name, expected_class) in expected_mappings.items():
        assert FailureClassifier.get_agent(category, use_class_name=False) == expected_name
        assert FailureClassifier.get_agent(category, use_class_name=True) == expected_class


def test_severity_assignments():
    """Verify severity level assignments across error categories."""
    assert FailureClassifier.get_severity("SyntaxError") == "CRITICAL"
    assert FailureClassifier.get_severity("DatabaseError") == "CRITICAL"
    assert FailureClassifier.get_severity("AuthenticationError") == "CRITICAL"
    assert FailureClassifier.get_severity("SecurityError") == "CRITICAL"
    assert FailureClassifier.get_severity("ImportError") == "HIGH"
    assert FailureClassifier.get_severity("BuildError") == "HIGH"
    assert FailureClassifier.get_severity("IntegrationError") == "HIGH"
    assert FailureClassifier.get_severity("DeploymentError") == "HIGH"
    assert FailureClassifier.get_severity("ConfigurationError") == "MEDIUM"
    assert FailureClassifier.get_severity("UnknownError") == "LOW"


def test_database_error_detection():
    """Verify database exceptions are classified properly."""
    db_err = sqlite3.OperationalError("no such table: users")
    res = FailureClassifier.classify(db_err)

    assert res.category == "DatabaseError"
    assert res.severity == "CRITICAL"
    assert res.agent_class == "DBAgent"
    assert res.component == "database"

