"""Self-Healing Foundation service for FORGE AI QA & DevOps module.

Provides a clean interface for orchestrator loop integration to track repair attempts,
enforce maximum repair limits, identify responsible agents, and dispatch repair contracts.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from backend.schemas.qa_schema import QAOutput, QAError
from backend.services.failure_classifier import FailureClassifier

MAX_REPAIR_ATTEMPTS = 3


class RepairRequest(BaseModel):
    """Structured contract describing a repair request to be dispatched to a responsible agent."""
    attempt_number: int = Field(..., description="Current repair attempt number (1..MAX_REPAIR_ATTEMPTS)")
    max_attempts: int = Field(default=MAX_REPAIR_ATTEMPTS, description="Maximum allowed repair attempts")
    responsible_agent: str = Field(..., description="Target agent class/name responsible for fixing the failure")
    affected_component: str = Field(..., description="Primary affected component (e.g. backend, database, frontend, auth)")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="List of classified QA error payloads")
    summary: str = Field(..., description="Human-readable summary of the required repair action")


class SelfHealingResult(BaseModel):
    """Evaluation output of the self-healing manager for an orchestration cycle."""
    action: str = Field(..., description="Action recommendation: 'proceed_to_deploy', 'request_repair', or 'max_attempts_exceeded'")
    attempt_count: int = Field(..., description="Current cumulative repair attempt count")
    max_attempts: int = Field(default=MAX_REPAIR_ATTEMPTS, description="Maximum repair attempts limit")
    repair_request: Optional[RepairRequest] = Field(default=None, description="Active repair request payload if repair is needed")
    message: str = Field(..., description="Detailed status explanation")


class SelfHealingManager:
    """Manages self-healing lifecycle, repair attempt counters, and agent repair requests."""

    def __init__(self, max_attempts: int = MAX_REPAIR_ATTEMPTS):
        self.max_attempts = max_attempts
        self.attempt_count = 0
        self.history: List[Dict[str, Any]] = []

    def reset(self) -> None:
        """Reset repair attempt counter and history state."""
        self.attempt_count = 0
        self.history.clear()

    def can_attempt_repair(self) -> bool:
        """Check whether another repair attempt is allowed."""
        return self.attempt_count < self.max_attempts

    def identify_responsible_agent(self, qa_data: Dict[str, Any]) -> tuple[str, str]:
        """Identify primary responsible agent name/class and affected component from QA output data."""
        errors = qa_data.get("errors", [])
        if errors:
            first_err = errors[0]
            if isinstance(first_err, dict):
                agent = first_err.get("agent") or FailureClassifier.get_agent(first_err.get("type", "UnknownError"), use_class_name=True)
                component = first_err.get("component") or first_err.get("affected_component") or "backend"
                return agent, component

        component = qa_data.get("affected_component") or "backend"
        category = "BuildError" if component == "frontend" else "SyntaxError" if component == "backend" else "DatabaseError" if component == "database" else "UnknownError"
        agent = FailureClassifier.get_agent(category, use_class_name=True)
        return agent, component

    def create_repair_request(self, qa_data: Dict[str, Any]) -> RepairRequest:
        """Generate a structured RepairRequest object for the current attempt."""
        agent, component = self.identify_responsible_agent(qa_data)
        errors = qa_data.get("errors", [])
        failed_count = qa_data.get("tests_failed", len(errors))
        summary = f"Attempt {self.attempt_count}/{self.max_attempts}: {failed_count} failure(s) detected in '{component}'. Assigned to {agent}."

        return RepairRequest(
            attempt_number=self.attempt_count,
            max_attempts=self.max_attempts,
            responsible_agent=agent,
            affected_component=component,
            errors=errors,
            summary=summary
        )

    def evaluate(self, qa_data: Dict[str, Any]) -> SelfHealingResult:
        """Evaluate QA execution data and determine next self-healing action."""
        is_passed = qa_data.get("status") == "passed" and qa_data.get("deployment_ready", True) and not qa_data.get("fix_required", False)

        if is_passed:
            return SelfHealingResult(
                action="proceed_to_deploy",
                attempt_count=self.attempt_count,
                max_attempts=self.max_attempts,
                repair_request=None,
                message="QA passed successfully. Application is ready for deployment."
            )

        # Increment attempt counter for failure case
        self.attempt_count += 1

        if self.attempt_count > self.max_attempts:
            summary = f"Maximum repair attempts ({self.max_attempts}) reached. Stopping self-healing loop."
            res = SelfHealingResult(
                action="max_attempts_exceeded",
                attempt_count=self.attempt_count,
                max_attempts=self.max_attempts,
                repair_request=None,
                message=summary
            )
            self.history.append(res.model_dump())
            return res

        repair_req = self.create_repair_request(qa_data)
        res = SelfHealingResult(
            action="request_repair",
            attempt_count=self.attempt_count,
            max_attempts=self.max_attempts,
            repair_request=repair_req,
            message=repair_req.summary
        )
        self.history.append(res.model_dump())
        return res
