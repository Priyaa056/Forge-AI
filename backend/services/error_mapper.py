"""Error Mapper service for FORGE AI QA & DevOps module."""

from typing import Any, Dict, Optional, Union, Type
import itertools

from backend.schemas.qa_schema import QAError
from backend.services.failure_classifier import FailureClassifier


class ErrorMapper:
    """Converts Python exceptions or raw error outputs into structured QAError objects."""

    def __init__(self, id_prefix: str = "QA"):
        self.id_prefix = id_prefix
        self._counter = itertools.count(1)

    def generate_id(self) -> str:
        """Generate a sequential QA error ID (e.g. QA-001)."""
        return f"{self.id_prefix}-{next(self._counter):03d}"

    def reset_counter(self) -> None:
        """Reset the ID generator sequence."""
        self._counter = itertools.count(1)

    def map_error(
        self,
        error: Union[Exception, Type[Exception], str, Dict[str, Any], Any],
        message: Optional[str] = None,
        suggestion: Optional[str] = None,
        component: Optional[str] = None,
        agent: Optional[str] = None,
        test_name: Optional[str] = None,
        error_id: Optional[str] = None,
        use_class_name: bool = True,
    ) -> QAError:
        """Convert a Python exception or error representation into a structured QAError object."""
        classification = FailureClassifier.classify(
            error,
            custom_suggestion=suggestion,
            use_class_name=use_class_name
        )

        # Determine error ID
        assigned_id = error_id or self.generate_id()

        # Determine detailed message
        if message:
            err_message = message
        elif isinstance(error, Exception):
            err_msg_str = str(error).strip()
            err_message = err_msg_str if err_msg_str else f"{type(error).__name__} occurred"
        elif isinstance(error, dict):
            err_message = str(error.get("message") or error.get("error") or classification.category)
        else:
            err_message = str(error)

        assigned_component = component or classification.component
        assigned_agent = agent or classification.agent
        assigned_suggestion = suggestion or classification.suggestion

        return QAError(
            id=assigned_id,
            type=classification.category,
            severity=classification.severity,
            component=assigned_component,
            agent=assigned_agent,
            message=err_message,
            suggestion=assigned_suggestion,
            test_name=test_name,
        )


# Global default mapper instance for easy utility calls
default_mapper = ErrorMapper()


def map_exception_to_qa_error(
    error: Union[Exception, Type[Exception], str, Dict[str, Any], Any],
    **kwargs
) -> QAError:
    """Convenience utility function to map any exception into a QAError."""
    return default_mapper.map_error(error, **kwargs)
