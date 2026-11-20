"""LLM client abstraction.

``USE_LLM=true`` turns LLM assistance on; ``LLM_PROVIDER`` picks the provider:

* ``gemini`` (default): Google Gemini with ``GOOGLE_API_KEY`` (and optional ``GEMINI_MODEL``).
* ``groq``: Groq's OpenAI-compatible API with ``GROQ_API_KEY`` (and optional ``GROQ_MODEL``).
* ``openai_compatible``: any OpenAI-compatible chat API (OpenRouter, a local server, ...) with
  ``LLM_BASE_URL``, ``LLM_API_KEY`` and ``LLM_MODEL``.

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
import time
from typing import Any, Dict, Optional, Protocol

import httpx

import backend.config  # noqa: F401  (loads backend/.env)

logger = logging.getLogger("forge.llm")

PLACEHOLDER_KEYS = {"", "your_gemini_api_key_here", "your_groq_api_key_here", "your_api_key_here", "changeme"}
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
PROVIDERS = ("gemini", "groq", "openai_compatible")


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


class OpenAICompatibleClient:
    """Chat-completions client for OpenAI-compatible APIs (Groq, OpenRouter, ...) over httpx.

    Asks for a JSON object when ``json_mode`` is set (and retries without it if the model does not
    support that), waits once on a rate limit, and never puts the API key in an error message.
    """

    def __init__(self, api_key: str, base_url: str, model_name: str, provider: str = "openai_compatible",
                 timeout_s: float = 90.0, max_tokens: Optional[int] = None,
                 transport: Optional[httpx.BaseTransport] = None):
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.provider = provider
        self.name = f"{provider}:{model_name}"
        self.max_tokens = max_tokens
        self._http = httpx.Client(timeout=timeout_s, transport=transport)

    def _post(self, body: Dict[str, Any]) -> httpx.Response:
        try:
            return self._http.post(f"{self.base_url}/chat/completions", json=body,
                                   headers={"Authorization": f"Bearer {self._api_key}"})
        except httpx.HTTPError as exc:  # network failure, timeout
            raise LLMError(f"{self.provider} request failed: {type(exc).__name__}") from exc

    @staticmethod
    def _error_text(response: httpx.Response) -> str:
        try:
            error = response.json().get("error")
            message = error.get("message") if isinstance(error, dict) else error
        except ValueError:
            message = response.text
        return str(message or response.reason_phrase)[:300]

    def generate_text(self, prompt: str, *, json_mode: bool = True) -> str:
        body: Dict[str, Any] = {"model": self.model_name, "messages": [{"role": "user", "content": prompt}],
                                "temperature": 0.2}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.max_tokens:
            body["max_tokens"] = self.max_tokens
        response = self._post(body)
        if response.status_code == 429:  # rate limited: wait as asked (briefly) and try once more
            try:
                wait = float(response.headers.get("retry-after", "5"))
            except ValueError:
                wait = 5.0
            time.sleep(min(max(wait, 1.0), 20.0))
            response = self._post(body)
        if response.status_code == 400 and json_mode and "response_format" in self._error_text(response):
            body.pop("response_format")  # this model has no JSON mode; the prompt still asks for JSON
            response = self._post(body)
        if response.status_code >= 400:
            raise LLMError(f"{self.provider} request failed: HTTP {response.status_code}: {self._error_text(response)}")
        try:
            content = response.json()["choices"][0]["message"].get("content")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"{self.provider} returned an unexpected response") from exc
        if not content:
            raise LLMError(f"{self.provider} returned an empty response")
        return content


def _max_tokens() -> Optional[int]:
    try:
        value = int(os.getenv("LLM_MAX_TOKENS", "0"))
    except ValueError:
        return None
    return value if value > 0 else None


def _build_client(provider: str) -> Optional[Any]:
    """Create the client for ``provider`` from the environment, or None when its key is missing."""
    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if api_key in PLACEHOLDER_KEYS:
            logger.warning("LLM_PROVIDER=groq but GROQ_API_KEY is not configured; using deterministic generators.")
            return None
        model = os.getenv("GROQ_MODEL", "").strip() or DEFAULT_GROQ_MODEL
        return OpenAICompatibleClient(api_key, GROQ_BASE_URL, model, provider="groq", max_tokens=_max_tokens())
    if provider == "openai_compatible":
        api_key = os.getenv("LLM_API_KEY", "").strip()
        base_url = os.getenv("LLM_BASE_URL", "").strip()
        model = os.getenv("LLM_MODEL", "").strip()
        if api_key in PLACEHOLDER_KEYS or not base_url.startswith(("http://", "https://")) or not model:
            logger.warning("LLM_PROVIDER=openai_compatible needs LLM_BASE_URL, LLM_API_KEY and LLM_MODEL; "
                           "using deterministic generators.")
            return None
        return OpenAICompatibleClient(api_key, base_url, model, provider="openai_compatible", max_tokens=_max_tokens())
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if api_key in PLACEHOLDER_KEYS:
        logger.warning("USE_LLM=true but GOOGLE_API_KEY is not configured; using deterministic generators.")
        return None
    return GeminiClient(api_key=api_key)


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
    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower() or "gemini"
    if provider not in PROVIDERS:
        logger.warning("Unknown LLM_PROVIDER=%r (expected one of %s); using deterministic generators.",
                       provider, ", ".join(PROVIDERS))
        return None
    try:
        return _build_client(provider)
    except Exception as exc:
        logger.warning("Could not initialise the %s client (%s); using deterministic generators.",
                       provider, type(exc).__name__)
        return None


def llm_mode() -> Dict[str, Any]:
    """Describe the active generation mode (for the dashboard and artifacts). Never exposes secrets."""
    client = get_llm_client()
    if client is None:
        return {
            "llm_enabled": False,
            "provider": None,
            "mode": "deterministic",
            "detail": "No LLM configured (set USE_LLM=true and a provider key, e.g. LLM_PROVIDER=groq with "
            "GROQ_API_KEY, in backend/.env). Agents use prompt-driven rule-based analysis.",
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
