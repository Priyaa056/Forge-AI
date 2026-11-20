"""LLM integration layer for FORGE AI agents (Google Gemini, Groq or any OpenAI-compatible API)."""

from .client import (
    LLMClient,
    LLMError,
    GeminiClient,
    OpenAICompatibleClient,
    get_llm_client,
    set_llm_client,
    llm_mode,
    extract_json,
)

__all__ = [
    "LLMClient",
    "LLMError",
    "GeminiClient",
    "OpenAICompatibleClient",
    "get_llm_client",
    "set_llm_client",
    "llm_mode",
    "extract_json",
]
