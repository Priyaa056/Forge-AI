"""Pydantic V2 schemas for QA Agent Output validation."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class TestSuiteSpec(BaseModel):
    """Specification for a QA test suite."""
    name: str = Field(..., description="Test suite name e.g. API Integration Tests, Auth Unit Tests")
    test_type: str = Field(default="unit", description="Test type: unit, integration, e2e")
    tests_count: int = Field(default=0, description="Total tests in suite")
    passed_count: int = Field(default=0, description="Passed tests count")
    failed_count: int = Field(default=0, description="Failed tests count")


class QAOutput(BaseModel):
    """QA Agent JSON output schema."""
    project_name: str = Field(..., description="Project name")
    total_tests: int = Field(default=0, description="Overall total test count")
    passed_tests: int = Field(default=0, description="Overall passed test count")
    failed_tests: int = Field(default=0, description="Overall failed test count")
    coverage_percentage: float = Field(default=100.0, description="Code test coverage percentage")
    test_suites: List[TestSuiteSpec] = Field(default_factory=list, description="Test suites executed")
    lint_status: str = Field(default="PASSED", description="Linter status e.g. PASSED, WARNINGS, FAILED")
    security_scan_status: str = Field(default="PASSED", description="Security scan status e.g. PASSED, VULNERABILITIES_FOUND")
    test_code_files: Dict[str, str] = Field(default_factory=dict, description="Generated test files mapping path to code")
    summary: Optional[str] = Field(default=None, description="QA report summary")
