"""Pydantic V2 schemas for QA Agent Output validation."""

from typing import List, Optional
from pydantic import BaseModel, Field


class QAErrorDetail(BaseModel):
    """Detailed information on a single test error."""
    test_name: str = Field(..., description="Name of the test or check that failed")
    error_type: str = Field(..., description="Type of error: SyntaxError, ImportError, EndpointError, DatabaseError, FrontendBuildError, DependencyError, ConfigurationError")
    message: str = Field(..., description="Detailed error message or stack trace snippet")
    affected_component: str = Field(..., description="Affected component or agent: 'backend', 'frontend', 'database', 'auth', 'pm'")
    suggested_fix: Optional[str] = Field(default=None, description="Suggested action for self-healing repair loop")


class QAOutput(BaseModel):
    """QA Agent JSON output schema."""
    status: str = Field(..., description="Overall QA status: 'passed' or 'failed'")
    tests_run: int = Field(default=0, description="Total number of tests executed")
    tests_passed: int = Field(default=0, description="Number of tests passed")
    tests_failed: int = Field(default=0, description="Number of tests failed")
    errors: List[QAErrorDetail] = Field(default_factory=list, description="List of detected error details")
    affected_component: Optional[str] = Field(default=None, description="Primary component affected if failures occurred")
    fix_required: bool = Field(default=False, description="Whether self-healing fix loop must be triggered")
    execution_timestamp: Optional[str] = Field(default=None, description="ISO timestamp of test execution")
