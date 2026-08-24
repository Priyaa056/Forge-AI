"""Tests for LLM validation failure propagation in BackendAgent, DBAgent, and AuthAgent.

Tests cover:
- CASE 1: Valid JSON matching Pydantic schema → Agent succeeds.
- CASE 2: Malformed JSON → Agent raises ValidationError (structured exception).
- CASE 3: Well-formed JSON but incorrect schema → Pydantic validation fails, ValidationError propagated, fallback NOT used.
"""

import json
from unittest.mock import MagicMock
import pytest

from backend.agents.backend_agent import BackendAgent
from backend.agents.db_agent import DBAgent
from backend.agents.auth_agent import AuthAgent
from backend.exceptions import ValidationError
from backend.schemas.backend_schema import BackendOutput
from backend.schemas.db_schema import DBOutput
from backend.schemas.auth_schema import AuthOutput


def _create_inputs(tmp_path):
    """Helper: create minimal input files required for agents."""
    pm_file = tmp_path / "pm_output.json"
    pm_data = {
        "project_name": "TestApp",
        "description": "Test App",
        "features": ["Auth Feature"],
        "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
        "database_entities": [
            {
                "name": "User",
                "fields": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "email", "type": "VARCHAR"},
                    {"name": "hashed_password", "type": "VARCHAR"}
                ]
            }
        ]
    }
    pm_file.write_text(json.dumps(pm_data), encoding="utf-8")

    backend_file = tmp_path / "backend_output.json"
    backend_agent = BackendAgent(pm_output_path=str(pm_file), output_filepath=str(backend_file))
    backend_agent.run()

    db_file = tmp_path / "db_output.json"
    db_agent = DBAgent(pm_output_path=str(pm_file), backend_output_path=str(backend_file), output_filepath=str(db_file))
    db_agent.run()

    return str(pm_file), str(backend_file), str(db_file)


# ---------------------------------------------------------------------------
# CASE 1: Valid JSON matching Pydantic schema -> agent succeeds
# ---------------------------------------------------------------------------

def test_llm_valid_json_succeeds(tmp_path, monkeypatch):
    pm_path, backend_path, db_path = _create_inputs(tmp_path)
    backend_out_path = str(tmp_path / "backend_llm_out.json")

    valid_backend_json = json.dumps({
        "project_name": "TestApp",
        "architecture": "Clean Architecture (Controller-Service-Repository)",
        "endpoints": [],
        "service_layer": [],
        "repository_layer": [],
        "global_dependencies": ["get_db"],
        "error_handlers": [
            {"status_code": 404, "exception_type": "HTTPException", "detail": "Not found"}
        ]
    })

    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = f"```json\n{valid_backend_json}\n```"
    mock_model.generate_content.return_value = mock_response

    agent = BackendAgent(pm_output_path=pm_path, output_filepath=backend_out_path)
    monkeypatch.setattr(agent, "get_gemini_model", lambda: mock_model)

    output = agent.run()

    assert isinstance(output, BackendOutput)
    assert output.project_name == "TestApp"
    mock_model.generate_content.assert_called_once()


# ---------------------------------------------------------------------------
# CASE 2: Malformed JSON -> agent raises structured ValidationError
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("agent_type", ["backend", "db", "auth"])
def test_llm_malformed_json_raises_validation_error(tmp_path, monkeypatch, agent_type):
    pm_path, backend_path, db_path = _create_inputs(tmp_path)
    out_path = str(tmp_path / f"{agent_type}_out.json")

    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "{ malformed json: missing quotes ... "
    mock_model.generate_content.return_value = mock_response

    if agent_type == "backend":
        agent = BackendAgent(pm_output_path=pm_path, output_filepath=out_path)
        expected_class = "BackendAgent"
    elif agent_type == "db":
        agent = DBAgent(pm_output_path=pm_path, backend_output_path=backend_path, output_filepath=out_path)
        expected_class = "DBAgent"
    else:
        agent = AuthAgent(pm_output_path=pm_path, backend_output_path=backend_path, db_output_path=db_path, output_filepath=out_path)
        expected_class = "AuthAgent"

    monkeypatch.setattr(agent, "get_gemini_model", lambda: mock_model)
    agent.load_inputs()

    with pytest.raises(ValidationError) as exc_info:
        agent.generate()

    err_msg = str(exc_info.value)
    assert expected_class in err_msg
    assert "schema validation failed" in err_msg
    assert "malformed JSON" in err_msg


# ---------------------------------------------------------------------------
# CASE 3: Well-formed JSON but incorrect schema -> Pydantic validation fails,
# ValidationError propagated, fallback generator NOT used.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("agent_type", ["backend", "db", "auth"])
def test_llm_incorrect_schema_json_raises_validation_error(tmp_path, monkeypatch, agent_type):
    pm_path, backend_path, db_path = _create_inputs(tmp_path)
    out_path = str(tmp_path / f"{agent_type}_out.json")

    # Well-formed JSON but missing required fields
    invalid_schema_json = json.dumps({
        "unknown_key": "some_value",
        "invalid_field": 123
    })

    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = invalid_schema_json
    mock_model.generate_content.return_value = mock_response

    if agent_type == "backend":
        agent = BackendAgent(pm_output_path=pm_path, output_filepath=out_path)
        expected_class = "BackendAgent"
    elif agent_type == "db":
        agent = DBAgent(pm_output_path=pm_path, backend_output_path=backend_path, output_filepath=out_path)
        expected_class = "DBAgent"
    else:
        agent = AuthAgent(pm_output_path=pm_path, backend_output_path=backend_path, db_output_path=db_path, output_filepath=out_path)
        expected_class = "AuthAgent"

    monkeypatch.setattr(agent, "get_gemini_model", lambda: mock_model)

    fallback_called = False
    original_fallback = agent._generate_fallback

    def mock_fallback():
        nonlocal fallback_called
        fallback_called = True
        return original_fallback()

    monkeypatch.setattr(agent, "_generate_fallback", mock_fallback)
    agent.load_inputs()

    with pytest.raises(ValidationError) as exc_info:
        agent.generate()

    err_msg = str(exc_info.value)
    assert expected_class in err_msg
    assert "schema validation failed" in err_msg
    assert not fallback_called, f"Fallback generator was silently called for {expected_class} when LLM output failed schema validation!"
