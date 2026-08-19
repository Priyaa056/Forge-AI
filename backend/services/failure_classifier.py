"""Failure Classifier service for FORGE AI QA & DevOps module."""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Union, Type
import sqlite3


@dataclass
class FailureClassification:
    """Structured representation of a classified failure."""
    category: str
    severity: str
    agent: str
    agent_class: str
    component: str
    suggestion: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert classification to dictionary."""
        return {
            "category": self.category,
            "severity": self.severity,
            "agent": self.agent,
            "agent_class": self.agent_class,
            "component": self.component,
            "suggestion": self.suggestion,
        }


class FailureClassifier:
    """Intelligent error classification system mapping errors to categories, severities, and agents."""

    SUPPORTED_CATEGORIES = {
        "ImportError",
        "SyntaxError",
        "DependencyError",
        "DatabaseError",
        "APIError",
        "BuildError",
        "ConfigurationError",
        "AuthenticationError",
        "IntegrationError",
        "DeploymentError",
        "SecurityError",
        "UnknownError",
        # Legacy Aliases
        "FrontendBuildError",
        "EndpointError",
    }

    SEVERITY_LEVELS = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}

    # Category -> Agent Name mapping
    AGENT_MAPPING = {
        "ImportError": "Backend Agent",
        "SyntaxError": "Backend Agent",
        "DependencyError": "Backend Agent",
        "DatabaseError": "DB Agent",
        "APIError": "Backend Agent",
        "EndpointError": "Backend Agent",
        "BuildError": "UI Agent",
        "FrontendBuildError": "UI Agent",
        "ConfigurationError": "PM Agent",
        "AuthenticationError": "Auth Agent",
        "IntegrationError": "QA Agent",
        "DeploymentError": "Deploy Agent",
        "SecurityError": "Auth Agent",
        "UnknownError": "QA Agent",
    }

    # Category -> Agent Class Name mapping
    AGENT_CLASS_MAPPING = {
        "ImportError": "BackendAgent",
        "SyntaxError": "BackendAgent",
        "DependencyError": "BackendAgent",
        "DatabaseError": "DBAgent",
        "APIError": "BackendAgent",
        "EndpointError": "BackendAgent",
        "BuildError": "UIAgent",
        "FrontendBuildError": "UIAgent",
        "ConfigurationError": "PMAgent",
        "AuthenticationError": "AuthAgent",
        "IntegrationError": "QAAgent",
        "DeploymentError": "DeployAgent",
        "SecurityError": "AuthAgent",
        "UnknownError": "QAAgent",
    }

    # Category -> Severity mapping
    SEVERITY_MAPPING = {
        "SyntaxError": "CRITICAL",
        "DatabaseError": "CRITICAL",
        "AuthenticationError": "CRITICAL",
        "SecurityError": "CRITICAL",
        "ImportError": "HIGH",
        "BuildError": "HIGH",
        "FrontendBuildError": "HIGH",
        "DependencyError": "HIGH",
        "APIError": "HIGH",
        "EndpointError": "HIGH",
        "IntegrationError": "HIGH",
        "DeploymentError": "HIGH",
        "ConfigurationError": "MEDIUM",
        "UnknownError": "LOW",
    }

    # Category -> Component mapping
    COMPONENT_MAPPING = {
        "ImportError": "backend",
        "SyntaxError": "backend",
        "DependencyError": "backend",
        "DatabaseError": "database",
        "APIError": "backend",
        "EndpointError": "backend",
        "BuildError": "frontend",
        "FrontendBuildError": "frontend",
        "ConfigurationError": "pm",
        "AuthenticationError": "auth",
        "IntegrationError": "integration",
        "DeploymentError": "deployment",
        "SecurityError": "auth",
        "UnknownError": "qa",
    }

    # Default Suggestions
    SUGGESTION_MAPPING = {
        "ImportError": "Check module paths and install missing dependencies.",
        "SyntaxError": "Fix syntax error in code file.",
        "DependencyError": "Install required package dependencies.",
        "DatabaseError": "Check database connectivity, schema definitions, and credentials.",
        "APIError": "Verify API endpoint route registrations and payload schemas.",
        "EndpointError": "Verify API endpoint route registrations and payload schemas.",
        "BuildError": "Check package.json build scripts and frontend build setup.",
        "FrontendBuildError": "Check package.json build scripts and frontend build setup.",
        "ConfigurationError": "Review configuration settings and environment variables.",
        "AuthenticationError": "Check authentication credentials, tokens, and security rules.",
        "IntegrationError": "Verify inter-service API contracts and communication pipelines.",
        "DeploymentError": "Check Docker configuration, container runtime logs, and deployment specs.",
        "SecurityError": "Review security permissions, credentials, and encryption settings.",
        "UnknownError": "Inspect stack trace and debug unexpected failure.",
    }

    @classmethod
    def detect_category(cls, error: Union[Exception, Type[Exception], str, Dict[str, Any], Any]) -> str:
        """Detect the supported error category from an exception, class, dict, or string."""
        if isinstance(error, str):
            if error in cls.SUPPORTED_CATEGORIES:
                return error
            err_lower = error.lower()
            if "import" in err_lower or "modulenotfound" in err_lower:
                return "ImportError"
            if "syntax" in err_lower or "indentation" in err_lower:
                return "SyntaxError"
            if "depend" in err_lower or "package" in err_lower:
                return "DependencyError"
            if "database" in err_lower or "sqlite" in err_lower or "sql" in err_lower or "db" in err_lower:
                return "DatabaseError"
            if "endpoint" in err_lower:
                return "EndpointError"
            if "api" in err_lower or "fastapi" in err_lower or "route" in err_lower:
                return "APIError"
            if "frontendbuild" in err_lower:
                return "FrontendBuildError"
            if "build" in err_lower or "vite" in err_lower or "webpack" in err_lower:
                return "BuildError"
            if "security" in err_lower:
                return "SecurityError"
            if "auth" in err_lower or "jwt" in err_lower or "token" in err_lower or "permission" in err_lower:
                return "AuthenticationError"
            if "deploy" in err_lower or "docker" in err_lower:
                return "DeploymentError"
            if "integration" in err_lower:
                return "IntegrationError"
            if "config" in err_lower or "secret" in err_lower or "env" in err_lower:
                return "ConfigurationError"
            return "UnknownError"

        if isinstance(error, dict):
            type_val = error.get("type") or error.get("error_type") or error.get("category")
            if type_val and str(type_val) in cls.SUPPORTED_CATEGORIES:
                return str(type_val)
            msg = str(error.get("message", "")) + " " + str(type_val or "")
            return cls.detect_category(msg)

        if isinstance(error, type) and issubclass(error, Exception):
            if issubclass(error, (ImportError, ModuleNotFoundError)):
                return "ImportError"
            if issubclass(error, SyntaxError):
                return "SyntaxError"
            if issubclass(error, (sqlite3.Error, sqlite3.OperationalError, sqlite3.DatabaseError)):
                return "DatabaseError"
            name = error.__name__
            if name in cls.SUPPORTED_CATEGORIES:
                return name
            return cls.detect_category(name)

        if isinstance(error, Exception):
            if isinstance(error, (ImportError, ModuleNotFoundError)):
                return "ImportError"
            if isinstance(error, SyntaxError):
                return "SyntaxError"
            if isinstance(error, (sqlite3.Error, sqlite3.OperationalError, sqlite3.DatabaseError)):
                return "DatabaseError"
            name = type(error).__name__
            if name in cls.SUPPORTED_CATEGORIES:
                return name
            msg = f"{name}: {str(error)}"
            return cls.detect_category(msg)

        return "UnknownError"

    @classmethod
    def get_severity(cls, category: str) -> str:
        """Get severity level for an error category."""
        return cls.SEVERITY_MAPPING.get(category, "LOW")

    @classmethod
    def get_agent(cls, category: str, use_class_name: bool = False) -> str:
        """Get responsible agent for an error category."""
        if use_class_name:
            return cls.AGENT_CLASS_MAPPING.get(category, "QAAgent")
        return cls.AGENT_MAPPING.get(category, "QA Agent")

    @classmethod
    def get_component(cls, category: str) -> str:
        """Get component associated with an error category."""
        return cls.COMPONENT_MAPPING.get(category, "qa")

    @classmethod
    def get_suggestion(cls, category: str) -> str:
        """Get default suggestion for an error category."""
        return cls.SUGGESTION_MAPPING.get(category, "Investigate and resolve error.")

    @classmethod
    def classify(
        cls,
        error: Union[Exception, Type[Exception], str, Dict[str, Any], Any],
        custom_suggestion: Optional[str] = None,
        use_class_name: bool = True,
    ) -> FailureClassification:
        """Classify an error and return a FailureClassification object."""
        category = cls.detect_category(error)
        severity = cls.get_severity(category)
        agent = cls.get_agent(category, use_class_name=False)
        agent_class = cls.get_agent(category, use_class_name=True)
        component = cls.get_component(category)
        suggestion = custom_suggestion or cls.get_suggestion(category)

        primary_agent = agent_class if use_class_name else agent

        return FailureClassification(
            category=category,
            severity=severity,
            agent=primary_agent,
            agent_class=agent_class,
            component=component,
            suggestion=suggestion,
        )
