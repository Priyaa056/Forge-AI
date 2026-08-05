"""Custom exception classes for FORGE AI Backend, DB, and Auth Agents."""

class AgentException(Exception):
    """Base exception for all agent operations."""
    pass

class MissingInputError(AgentException):
    """Raised when a required input JSON file is missing."""
    pass

class ValidationError(AgentException):
    """Raised when JSON input/output fails Pydantic schema validation."""
    pass

class GenerationError(AgentException):
    """Raised when specification generation fails."""
    pass
