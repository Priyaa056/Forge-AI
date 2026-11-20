"""LLM integration: client configuration, JSON extraction, LLM-driven PM/UI agents and visible fallbacks."""

import json

import pytest

from backend.agents.pm_agent import PMAgent
from backend.agents.ui_agent import UIAgent
from backend.llm.client import LLMError, extract_json, get_llm_client, llm_mode, set_llm_client

from .conftest import TASK_PROMPT

LLM_REQUIREMENTS = {
    "project_name": "FitTrack",
    "description": "Track gym workouts",
    "app_type": "fitness",
    "features": ["Log workouts"],
    "user_roles": [{"name": "admin", "is_admin": True}, {"name": "member", "description": "Gym member"}],
    "database_entities": [
        {"name": "Workout", "access": "owner", "display_field": "title",
         "fields": [{"name": "title", "type": "string", "nullable": False, "searchable": True},
                    {"name": "minutes", "type": "integer", "min_value": 0},
                    {"name": "intensity", "type": "enum", "enum_values": ["low", "high"]},
                    {"name": "exercise", "type": "reference", "references": "Exercise"}]},
        {"name": "Exercise", "access": "admin_managed", "fields": [{"name": "name", "type": "string", "nullable": False}]},
    ],
}


def test_extract_json_handles_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Here you go: {"a": {"b": 2}} thanks') == {"a": {"b": 2}}
    with pytest.raises(LLMError):
        extract_json("no json here")
    with pytest.raises(LLMError):
        extract_json("[1, 2]")


def test_client_disabled_without_configuration(monkeypatch):
    monkeypatch.setenv("USE_LLM", "true")
    monkeypatch.setenv("GOOGLE_API_KEY", "your_gemini_api_key_here")
    assert get_llm_client() is None
    assert llm_mode()["mode"] == "deterministic"
    monkeypatch.setenv("USE_LLM", "false")
    monkeypatch.setenv("GOOGLE_API_KEY", "anything")
    assert get_llm_client() is None


def test_pm_agent_uses_llm_requirements(fake_llm, tmp_path):
    client = fake_llm(json.dumps(LLM_REQUIREMENTS))
    agent = PMAgent(user_prompt="A fitness tracker where members log workouts and admins manage exercises",
                    output_filepath=str(tmp_path / "req.json"))
    out = agent.run()
    assert out.generation_mode == "llm" and agent.generation_mode == "llm"
    names = [e.name for e in out.database_entities]
    assert names == ["User", "Exercise", "Workout"]  # normalized + dependency ordered
    workout = {f.name: f for f in out.database_entities[2].fields}
    assert workout["exercise_id"].references == "Exercise"
    assert {r.name for r in out.user_roles} == {"admin", "member"}
    assert "fitness tracker" in client.prompts[0]


def test_pm_agent_retries_then_falls_back_visibly(fake_llm, tmp_path):
    fake_llm("not json at all", LLMError("quota exceeded"))
    agent = PMAgent(user_prompt=TASK_PROMPT, output_filepath=str(tmp_path / "req.json"))
    out = agent.run()
    assert out.generation_mode == "deterministic_fallback"
    assert any("Falling back" in note for note in agent.notes)
    assert "Task" in [e.name for e in out.database_entities]


def test_pm_agent_does_not_call_llm_for_invalid_prompt(fake_llm, tmp_path):
    from backend.agents.pm_analysis import PromptValidationError

    client = fake_llm()
    with pytest.raises(PromptValidationError):
        PMAgent(user_prompt="hi", output_filepath=str(tmp_path / "r.json")).run()
    assert client.prompts == []


def test_ui_agent_applies_validated_llm_styling(fake_llm, tmp_path):
    pm_path = tmp_path / "req.json"
    set_llm_client(None, force=False)
    PMAgent(user_prompt=TASK_PROMPT, output_filepath=str(pm_path)).run()
    fake_llm(json.dumps({"primary_color": "#123abc", "tagline": "Get things done, together.", "design_system_notes": "Calm"}))
    ui = UIAgent(pm_output_path=str(pm_path), output_filepath=str(tmp_path / "ui.json")).run()
    assert ui.styling_requirements.primary_color == "#123abc"


def test_ui_agent_rejects_invalid_llm_styling(fake_llm, tmp_path):
    pm_path = tmp_path / "req.json"
    PMAgent(user_prompt=TASK_PROMPT, output_filepath=str(pm_path)).run()
    fake_llm(json.dumps({"primary_color": "red; drop table", "tagline": ""}))
    agent = UIAgent(pm_output_path=str(pm_path), output_filepath=str(tmp_path / "ui.json"))
    ui = agent.run()
    assert ui.styling_requirements.primary_color.startswith("#") and len(ui.styling_requirements.primary_color) == 7
    assert agent.generation_mode == "deterministic_fallback"
