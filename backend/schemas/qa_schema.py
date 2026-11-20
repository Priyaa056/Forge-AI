"""Pydantic V2 schemas for the QA Agent output (``qa_report.json``).

Combines the structured error model from feature/qa-deploy (QAError, severity/agent classification)
with per-check and per-test results produced by actually executing the generated application's tests.
"""

from typing import Any, Dict, List, Optional

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
        return self.type

    @property
    def affected_component(self) -> str:
        return self.component

    @property
    def suggested_fix(self) -> Optional[str]:
        return self.suggestion


class QAErrorDetail(QAError):
    """Detailed information on a single test error (backward compatible model)."""

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
            data.setdefault("id", "QA-000")
            data.setdefault("severity", "HIGH")
            data.setdefault("agent", "BackendAgent")
        return data


class QACheck(BaseModel):
    """One executed verification step."""
    name: str
    category: str = Field(default="backend", description="static | backend | database | integration | frontend")
    status: str = Field(..., description="passed | failed | skipped")
    duration_ms: float = 0.0
    details: str = ""


class TestCaseResult(BaseModel):
    suite: str
    name: str
    status: str = Field(..., description="passed | failed | error | skipped")
    duration_ms: float = 0.0
    message: Optional[str] = None


class TestSuiteSpec(BaseModel):
    """Aggregated results for one generated test module."""
    name: str
    test_type: str = Field(default="integration")
    tests_count: int = 0
    passed_count: int = 0
    failed_count: int = 0


class QAOutput(BaseModel):
    """QA Agent JSON output schema."""

    project_name: Optional[str] = Field(default=None, description="Project under test")
    status: str = Field(..., description="Overall QA status: 'passed' or 'failed'")
    tests_run: int = Field(default=0, description="Total number of tests executed")
    tests_passed: int = Field(default=0, description="Number of tests passed")
    tests_failed: int = Field(default=0, description="Number of tests failed")
    errors: List[QAError] = Field(default_factory=list, description="List of structured QA error objects")
    critical_errors: int = Field(default=0, description="Number of critical severity errors detected")
    warnings: int = Field(default=0, description="Number of non-critical errors detected")
    score: float = Field(default=0.0, description="Percentage of executed checks/tests that passed (0-100)")
    deployment_ready: bool = Field(default=False, description="Whether code is ready for deployment")
    next_step: str = Field(default="", description="Recommended next action")
    affected_component: Optional[str] = Field(default=None, description="Primary component affected if failures occurred")
    fix_required: bool = Field(default=False, description="Whether a repair/regeneration is required")
    execution_timestamp: Optional[str] = Field(default=None, description="ISO timestamp of test execution")

    checks: List[QACheck] = Field(default_factory=list, description="Executed verification steps")
    test_suites: List[TestSuiteSpec] = Field(default_factory=list, description="Per-module test results")
    test_results: List[TestCaseResult] = Field(default_factory=list, description="Per-test results")
    frontend_build: str = Field(default="skipped", description="passed | failed | skipped")
    generated_test_files: List[str] = Field(default_factory=list)
    summary: Optional[str] = Field(default=None, description="QA report summary")
    repair_recommendation: Optional[str] = Field(default=None, description="Responsible agent and action from the self-healing manager")
    requirement_coverage: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Every specification item (module, entity, field, role, permission, workflow, rule, metric, seed) "
                    "with the generated evidence that implements it: covered | missing | unsupported")
    correction_tasks: List[Dict[str, Any]] = Field(
        default_factory=list, description="Targeted correction tasks for the agents responsible for missing requirements")
    unsupported_requests: List[str] = Field(default_factory=list, description="Requested capabilities the generator cannot provide")
    regression: Optional[Dict[str, Any]] = Field(
        default=None, description="Refinements: requirements and tests that passed in the refined version, re-checked")
