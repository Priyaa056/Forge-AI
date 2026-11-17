"""Exceptions for the FORGE AI platform and its agents."""


class ForgeAIError(Exception):
    """Base exception for FORGE AI platform errors."""


# Backwards-compatible alias used by the Backend/DB/Auth agents.
AgentException = ForgeAIError


class MissingInputError(ForgeAIError):
    """Raised when a required input (file or upstream artifact) is missing."""


class ValidationError(ForgeAIError):
    """Raised when input or output content fails schema validation."""


class GenerationError(ForgeAIError):
    """Raised when generation fails unrecoverably."""
