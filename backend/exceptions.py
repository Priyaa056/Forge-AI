"""Exceptions for FORGE AI platform."""


class ForgeAIError(Exception):
    """Base exception for FORGE AI platform errors."""
    pass


class MissingInputError(ForgeAIError):
    """Raised when an expected input file does not exist on disk."""
    pass


class ValidationError(ForgeAIError):
    """Raised when input file content is empty, malformed, or missing mandatory schema fields."""
    pass


class GenerationError(ForgeAIError):
    """Raised when generation process fails unrecoverably."""
    pass
