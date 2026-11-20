"""Unit tests for BackendAgent."""

import json
import pytest
from pathlib import Path

from backend.agents.backend_agent import BackendAgent
from backend.schemas.backend_schema import BackendOutput
from backend.exceptions import MissingInputError, ValidationError


def test_backend_agent_missing_input(tmp_path):
    agent = BackendAgent(
        pm_output_path=str(tmp_path / "non_existent.json"),
        output_filepath=str(tmp_path / "backend_output.json")
    )
    with pytest.raises(MissingInputError):
        agent.run()


def test_backend_agent_invalid_json(tmp_path):
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("not json content", encoding="utf-8")

    agent = BackendAgent(
        pm_output_path=str(invalid_file),
        output_filepath=str(tmp_path / "backend_output.json")
    )
    with pytest.raises(ValidationError):
        agent.run()


