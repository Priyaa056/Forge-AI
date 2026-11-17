"""LLM client abstraction.

Real execution uses Google Gemini when ``USE_LLM=true`` and ``GOOGLE_API_KEY`` is configured.
When no LLM is configured, agents run their deterministic, prompt-driven generators and every
artifact records ``generation_mode`` so the dashboard can show which mode produced it.

Tests inject a fake client with :func:`set_llm_client`; mock responses are never used on the
real execution path.
"""

import json
import logging
import os
import re
import threading
from typing import Any, Dict, Optional, Protocol

import backend.config  # noqa: F401  (loads backend/.env)

logger = logging.getLogger("forge.llm")

PLACEHOLDER_KEYS = {"", "your_gemini_api_key_here", "changeme"}


class LLMError(Exception):
    """Raised when the LLM call fails or returns unusable output."""


class LLMClient(Protocol):
    name: str

    def generate_text(self, prompt: str, *, json_mode: bool = True) -> str:  # pragma: no cover - protocol
        ...


class GeminiClient:
    """Thin wrapper around google-generativeai with JSON output mode and a request timeout."""

    def __init__(self, api_key: str, model_name: Optional[str] = None, timeout_s: float = 90.0):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import google.generativeai as genai  # deprecated SDK, but it is the project's existing integration

        self._genai = genai
        self._genai.configure(api_key=api_key)
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.name = f"gemini:{self.model_name}"
        self.timeout_s = timeout_s

    def generate_text(self, prompt: str, *, json_mode: bool = True) -> str:
        config: Dict[str, Any] = {"temperature": 0.2}
        if json_mode:
            config["response_mime_type"] = "application/json"
        try:
            model = self._genai.GenerativeModel(self.model_name, generation_config=config)
            response = model.generate_content(prompt, request_options={"timeout": self.timeout_s})
            text = getattr(response, "text", None)
        except Exception as exc:  # network, quota, auth, safety block
            raise LLMError(f"Gemini request failed: {type(exc).__name__}: {exc}") from exc
        if not text:
            raise LLMError("Gemini returned an empty response")
        return text


_override_lock = threading.Lock()
_override_client: Optional[Any] = None
_override_set = False


def set_llm_client(client: Optional[Any], *, force: bool = True) -> None:
    """Install a client for all agents (used by tests). ``set_llm_client(None, force=False)`` clears it."""
    global _override_client, _override_set
    with _override_lock:
        _override_client = client
        _override_set = force


def get_llm_client() -> Optional[Any]:
    """Return the configured LLM client, or None when the deterministic generators should run."""
    if _override_set:
        return _override_client
    if os.getenv("USE_LLM", "false").strip().lower() != "true":
        return None
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if api_key in PLACEHOLDER_KEYS:
        logger.warning("USE_LLM=true but GOOGLE_API_KEY is not configured; using deterministic generators.")
        return None
    try:
        return GeminiClient(api_key=api_key)
    except Exception as exc:
        logger.warning("Could not initialise Gemini client (%s); using deterministic generators.", exc)
        return None


def llm_mode() -> Dict[str, Any]:
    """Describe the active generation mode (for the dashboard and artifacts). Never exposes secrets."""
    client = get_llm_client()
    if client is None:
        return {
            "llm_enabled": False,
            "provider": None,
            "mode": "deterministic",
            "detail": "No LLM configured (set USE_LLM=true and GOOGLE_API_KEY in backend/.env). "
            "Agents use prompt-driven rule-based analysis.",
        }
    return {"llm_enabled": True, "provider": getattr(client, "name", "llm"), "mode": "llm", "detail": "LLM-assisted generation"}


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> Dict[str, Any]:
    """Parse a JSON object from LLM output, tolerating markdown fences and leading prose."""
    if text is None:
        raise LLMError("No LLM output to parse")
    cleaned = _FENCE_RE.sub("", text.strip()).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("LLM output did not contain a JSON object")
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM returned malformed JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise LLMError("LLM output must be a JSON object")
    return value
