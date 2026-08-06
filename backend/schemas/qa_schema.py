"""Pydantic V2 schemas for QA Agent Output validation."""

from typing import List, Optional, Any
from pydantic import BaseModel, Field, model_validator


class QAError(BaseModel):
    """Structured QA Error model representing classified failures."""

    id: str = Field(..., description="Unique identifier for the error, e.g. QA-001")
    type: str = Field(..., description="Error category type, e.g. SyntaxError, ImportError")
    severity: str = Field(..., description="Severity level: CRITICAL, HIGH, MEDIUM, LOW")
    component: str = Field(..., description="Affected component: backend, database, auth, pm, frontend, qa")
    agent: str = Field(..., description="Responsible FORGE AI agent name or class name")
    message: str = Field(..., description="Detailed error message")
    suggestion: Optional[str] = Field(default=None, description="Suggested fix or resolution action")
    test_name: Optional[str] = Field(default=None, description="Optional name of failing test or check")

    @property
    def error_type(self) -> str:
        """Backward compatibility alias for type."""
        return self.type

    @property
    def affected_component(self) -> str:
        """Backward compatibility alias for component."""
        return self.component

    @property
    def suggested_fix(self) -> Optional[str]:
        """Backward compatibility alias for suggestion."""
        return self.suggestion


class QAErrorDetail(QAError):
    """Detailed information on a single test error (Backward compatible model)."""

    @model_validator(mode="before")
    @classmethod
    def map_legacy_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "error_type" in data and "type" not in data:
                data["type"] = data["error_type"]
            if "affected_component" in data and "component" not in data:
                data["component"] = data["affected_component"]
            if "suggested_fix" in data and "suggestion" not in data:
                data["suggestion"] = data["suggested_fix"]
            if "id" not in data:
                data["id"] = "QA-000"
            if "severity" not in data:
                data["severity"] = "HIGH"
            if "agent" not in data:
                data["agent"] = "BackendAgent"
        return data


class QAOutput(BaseModel):
    """QA Agent JSON output schema."""

    status: str = Field(..., description="Overall QA status: 'passed' or 'failed'")
    tests_run: int = Field(default=0, description="Total number of tests executed")
    tests_passed: int = Field(default=0, description="Number of tests passed")
    tests_failed: int = Field(default=0, description="Number of tests failed")
    errors: List[QAError] = Field(default_factory=list, description="List of structured QA error objects")
    critical_errors: int = Field(default=0, description="Number of critical severity errors detected")
    warnings: int = Field(default=0, description="Number of warning severity (HIGH/MEDIUM/LOW) errors detected")
    score: float = Field(default=100.0, description="Quality assurance score percentage (0-100)")
    deployment_ready: bool = Field(default=True, description="Whether code is ready for deployment")
    next_step: str = Field(default="Deployment ready", description="Recommended next action")

    # Backward compatibility fields
    affected_component: Optional[str] = Field(default=None, description="Primary component affected if failures occurred")
    fix_required: bool = Field(default=False, description="Whether self-healing fix loop must be triggered")
    execution_timestamp: Optional[str] = Field(default=None, description="ISO timestamp of test execution")
