"""Provider selection and the Groq / OpenAI-compatible client (HTTP is mocked; no real API calls)."""

import json

import httpx
import pytest

from backend.llm import client as llm
from backend.llm.client import LLMError, OpenAICompatibleClient, get_llm_client, llm_mode
from backend.monitoring.logger import sanitize_secret

GROQ_KEY = "gsk_" + "a1B2c3D4" * 6


def make_client(handler, **kwargs):
    return OpenAICompatibleClient(GROQ_KEY, "https://api.groq.com/openai/v1", "test-model", provider="groq",
                                  transport=httpx.MockTransport(handler), **kwargs)


def reply(content, status=200):
    return httpx.Response(status, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


def test_groq_is_selected_from_the_environment(monkeypatch):
    monkeypatch.setenv("USE_LLM", "true")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", GROQ_KEY)
    client = get_llm_client()
    assert isinstance(client, OpenAICompatibleClient)
    assert client.name == f"groq:{llm.DEFAULT_GROQ_MODEL}" and client.base_url == llm.GROQ_BASE_URL
    monkeypatch.setenv("GROQ_MODEL", "some/other-model")
    assert get_llm_client().name == "groq:some/other-model"
    mode = llm_mode()
    assert mode["mode"] == "llm" and mode["provider"] == "groq:some/other-model"
    assert GROQ_KEY not in json.dumps(mode)


@pytest.mark.parametrize("env", [
    {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "your_groq_api_key_here"},          # placeholder key
    {"LLM_PROVIDER": "groq"},                                                     # no key
    {"LLM_PROVIDER": "openai_compatible", "LLM_API_KEY": "k" * 30, "LLM_MODEL": "m"},  # no base URL
    {"LLM_PROVIDER": "openai_compatible", "LLM_BASE_URL": "https://x.test/v1", "LLM_API_KEY": "k" * 30},  # no model
    {"LLM_PROVIDER": "somebody-else", "GROQ_API_KEY": GROQ_KEY},                  # unknown provider
])
def test_incomplete_configuration_falls_back_to_rules(monkeypatch, env):
    monkeypatch.setenv("USE_LLM", "true")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert get_llm_client() is None
    assert llm_mode()["mode"] == "deterministic"


def test_use_llm_false_wins(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", GROQ_KEY)
    assert get_llm_client() is None  # conftest sets USE_LLM=false


def test_openai_compatible_provider(monkeypatch):
    monkeypatch.setenv("USE_LLM", "true")
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_BASE_URL", "https://openrouter.ai/api/v1/")
    monkeypatch.setenv("LLM_API_KEY", "sk-or-v1-" + "0" * 40)
    monkeypatch.setenv("LLM_MODEL", "vendor/model:free")
    monkeypatch.setenv("LLM_MAX_TOKENS", "4096")
    client = get_llm_client()
    assert client.name == "openai_compatible:vendor/model:free"
    assert client.base_url == "https://openrouter.ai/api/v1" and client.max_tokens == 4096


def test_request_shape_and_json_mode():
    seen = []

    def handler(request):
        seen.append(request)
        return reply('{"ok": true}')

    out = make_client(handler, max_tokens=2048).generate_text("Return JSON please")
    assert out == '{"ok": true}'
    request = seen[0]
    assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {GROQ_KEY}"
    body = json.loads(request.content)
    assert body["model"] == "test-model" and body["messages"] == [{"role": "user", "content": "Return JSON please"}]
    assert body["response_format"] == {"type": "json_object"} and body["max_tokens"] == 2048
    make_client(handler).generate_text("plain", json_mode=False)
    assert "response_format" not in json.loads(seen[1].content) and "max_tokens" not in json.loads(seen[1].content)


def test_model_without_json_mode_is_retried_without_it():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "response_format json_object is not supported"}})
        return reply('{"ok": 1}')

    assert make_client(handler).generate_text("JSON") == '{"ok": 1}'
    assert len(bodies) == 2 and "response_format" not in bodies[1]


def test_rate_limit_waits_once_then_retries(monkeypatch):
    waits = []
    monkeypatch.setattr(llm.time, "sleep", waits.append)
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "3"}, json={"error": {"message": "Rate limit reached"}})
        return reply('{"ok": 2}')

    assert make_client(handler).generate_text("JSON") == '{"ok": 2}'
    assert waits == [3.0] and len(calls) == 2


@pytest.mark.parametrize("response, message", [
    (httpx.Response(401, json={"error": {"message": "Invalid API Key"}}), "HTTP 401: Invalid API Key"),
    (httpx.Response(500, text="upstream exploded"), "HTTP 500"),
    (httpx.Response(200, json={"choices": []}), "unexpected response"),
    (httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}), "empty response"),
])
def test_failures_raise_llm_errors_without_the_key(response, message):
    with pytest.raises(LLMError) as err:
        make_client(lambda request: response).generate_text("JSON")
    assert message in str(err.value) and GROQ_KEY not in str(err.value)


def test_network_errors_become_llm_errors():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(LLMError, match="groq request failed: ConnectError"):
        make_client(handler).generate_text("JSON")


def test_provider_keys_are_redacted_and_kept_from_generated_apps(monkeypatch, tmp_path):
    assert GROQ_KEY not in sanitize_secret(f"auth failed for {GROQ_KEY}")
    assert "[REDACTED_GROQ_KEY]" in sanitize_secret(f"key={GROQ_KEY}")
    from backend.services.app_runner import GeneratedAppProcess

    monkeypatch.setenv("GROQ_API_KEY", GROQ_KEY)
    monkeypatch.setenv("LLM_API_KEY", "secret-value-123")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    env = GeneratedAppProcess(app_root=tmp_path, data_dir=tmp_path / "data").env()  # not started
    assert not {"GROQ_API_KEY", "LLM_API_KEY", "LLM_PROVIDER"} & set(env)
    assert GROQ_KEY not in json.dumps(env)
