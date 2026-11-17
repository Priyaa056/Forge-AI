"""Unit tests for PipelineOrchestrationEngine."""

import json
import pytest
from pathlib import Path

from backend.schemas.pm_schema import PMOutput, TechStack, DatabaseEntity, DatabaseField
from backend.orchestration.pipeline import (
    PipelineOrchestrationEngine,
    PipelineStage,
    PipelineResult,
)


@pytest.fixture
def sample_pm_spec():
    return PMOutput(
        project_name="TaskFlow",
        description="Streamlined task management application",
        features=["User auth", "Tasks CRUD"],
        tech_stack=TechStack(frontend="React", backend="FastAPI", database="SQLite"),
        database_entities=[
            DatabaseEntity(
                name="User",
                fields=[
                    DatabaseField(name="id", type="INTEGER"),
                    DatabaseField(name="email", type="VARCHAR"),
                ],
            ),
            DatabaseEntity(
                name="Task",
                fields=[
                    DatabaseField(name="id", type="INTEGER"),
                    DatabaseField(name="title", type="VARCHAR"),
                ],
            ),
        ],
    )


def test_pipeline_engine_success(tmp_path, sample_pm_spec):
    output_dir = tmp_path / "custom_pipeline_output"
    callbacks_received = []

    def on_progress(stage, message):
        callbacks_received.append((stage, message))

    engine = PipelineOrchestrationEngine(
        output_dir=output_dir,
        progress_callback=on_progress,
    )

    assert engine.current_stage == PipelineStage.IDLE

    result = engine.run(sample_pm_spec)

    assert isinstance(result, PipelineResult)
    assert result.success is True
    assert result.final_stage == PipelineStage.COMPLETED
    assert result.error is None
    assert engine.current_stage == PipelineStage.COMPLETED

    # Check generated files
    assert (output_dir / "pm_output.json").is_file()
    assert (output_dir / "backend_output.json").is_file()
    assert (output_dir / "db_output.json").is_file()
    assert (output_dir / "auth_output.json").is_file()
    assert (output_dir / "ui_output.json").is_file()
    assert (output_dir / "frontend").is_dir()

    # Check artifacts map
    assert "pm_spec" in result.artifacts
    assert "backend_spec" in result.artifacts
    assert "db_spec" in result.artifacts
    assert "auth_spec" in result.artifacts
    assert "ui_spec" in result.artifacts
    assert "frontend_dir" in result.artifacts

    # Check callbacks triggered
    stages_triggered = [c[0] for c in callbacks_received]
    assert PipelineStage.PM_SPEC_LOADED in stages_triggered
    assert PipelineStage.BACKEND_GENERATED in stages_triggered
    assert PipelineStage.DB_GENERATED in stages_triggered
    assert PipelineStage.AUTH_GENERATED in stages_triggered
    assert PipelineStage.UI_GENERATED in stages_triggered
    assert PipelineStage.REACT_CODE_GENERATED in stages_triggered
    assert PipelineStage.COMPLETED in stages_triggered


def test_pipeline_engine_dict_input(tmp_path):
    output_dir = tmp_path / "dict_pipeline_output"
    engine = PipelineOrchestrationEngine(output_dir=output_dir)

    raw_spec = {
        "project_name": "DictApp",
        "description": "App built from dict spec",
        "features": ["Feature 1"],
        "database_entities": [
            {
                "name": "Item",
                "fields": [{"name": "id", "type": "INTEGER"}],
            }
        ],
    }

    result = engine.run(raw_spec)
    assert result.success is True
    assert result.final_stage == PipelineStage.COMPLETED
    assert (output_dir / "pm_output.json").is_file()


def test_pipeline_engine_failure_handling(tmp_path):
    output_dir = tmp_path / "fail_pipeline_output"
    engine = PipelineOrchestrationEngine(output_dir=output_dir)

    invalid_spec = {"description": "Missing project_name field"}

    result = engine.run(invalid_spec)

    assert result.success is False
    assert result.final_stage == PipelineStage.FAILED
    assert result.error is not None
    assert engine.current_stage == PipelineStage.FAILED
