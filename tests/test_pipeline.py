"""Tests for FORGE AI Orchestration Pipeline service and schemas."""

import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from backend.schemas.pm_schema import PMOutput
from backend.schemas.ui_schema import UIOutput
from backend.schemas.qa_schema import QAOutput
from backend.schemas.deploy_schema import DeployOutput
from backend.services.pipeline import (
    ForgePipeline,
    AgentStatus,
    PipelineStage,
    STAGE_ORDER,
)


def test_pm_output_validation():
    """Test validation of existing pm_output.json against PMOutput schema."""
    pm_path = Path("outputs/pm_output.json")
    assert pm_path.exists(), "outputs/pm_output.json must exist"

    with open(pm_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    pm_out = PMOutput.model_validate(data)
    assert pm_out.project_name == "TaskFlow"
    assert len(pm_out.features) > 0
    assert len(pm_out.database_entities) > 0


def test_pipeline_initialization(tmp_path):
    """Test pipeline initialization state."""
    pipeline = ForgePipeline(
        user_prompt="Build an e-commerce platform",
        project_id="test_proj_123",
        output_dir=str(tmp_path)
    )

    summary = pipeline.get_status_summary()
    assert summary["project_id"] == "test_proj_123"
    assert summary["user_prompt"] == "Build an e-commerce platform"
    assert summary["execution_status"] == AgentStatus.PENDING.value
    assert summary["current_agent"] is None

    for stage in STAGE_ORDER:
        assert summary["agent_statuses"][stage.value] == AgentStatus.PENDING.value


def test_pipeline_full_execution(tmp_path):
    """Test complete 7-stage pipeline execution PM -> UI -> Backend -> DB -> Auth -> QA -> Deploy."""
    # Copy pm_output.json to temp dir for stage execution
    pm_src = Path("outputs/pm_output.json")
    pm_dst = tmp_path / "pm_output.json"
    pm_dst.write_text(pm_src.read_text(encoding="utf-8"), encoding="utf-8")

    pipeline = ForgePipeline(
        user_prompt="Build a task app",
        output_dir=str(tmp_path)
    )

    state = pipeline.run_pipeline()
    assert state.execution_status == AgentStatus.COMPLETED
    assert state.current_agent is None

    summary = pipeline.get_status_summary()
    assert summary["execution_status"] == AgentStatus.COMPLETED
    assert len(summary["completed_stages"]) == 7

    for stage in STAGE_ORDER:
        assert summary["agent_statuses"][stage.value] == AgentStatus.COMPLETED
        stage_file = tmp_path / f"{stage.value}_output.json"
        assert stage_file.exists()


def test_pipeline_status_transitions(tmp_path):
    """Test pipeline status transitions during stage execution."""
    pipeline = ForgePipeline(output_dir=str(tmp_path))

    assert pipeline.state.execution_status == AgentStatus.PENDING

    # Run single stage PM
    pm_out = pipeline.run_stage(PipelineStage.PM)
    assert isinstance(pm_out, PMOutput)
    assert pipeline.state.agent_statuses[PipelineStage.PM] == AgentStatus.COMPLETED
    assert pipeline.state.agent_statuses[PipelineStage.UI] == AgentStatus.PENDING


def test_invalid_agent_output_handling(tmp_path):
    """Test that invalid handler output raises ValidationError and sets stage status to FAILED."""
    pipeline = ForgePipeline(output_dir=str(tmp_path))

    # Register an invalid handler for UI stage missing required fields or returning bad format
    def invalid_ui_handler(ctx):
        return {"invalid_key": 123}  # Missing required project_name

    pipeline.register_agent_handler(PipelineStage.UI, invalid_ui_handler)

    with pytest.raises(ValidationError):
        pipeline.run_stage(PipelineStage.UI)

    assert pipeline.state.agent_statuses[PipelineStage.UI] == AgentStatus.FAILED
    assert pipeline.state.execution_status == AgentStatus.FAILED
    assert "ui" in pipeline.state.error_reports


def test_agent_failure_and_retry_handling(tmp_path):
    """Test stage failure handling and retry mechanism."""
    pipeline = ForgePipeline(output_dir=str(tmp_path))

    call_count = 0

    def flaky_qa_handler(ctx):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Simulated QA agent connection failure")
        return {
            "project_name": "TaskFlow",
            "total_tests": 10,
            "passed_tests": 10,
            "failed_tests": 0,
            "coverage_percentage": 95.0,
            "lint_status": "PASSED",
            "security_scan_status": "PASSED"
        }

    pipeline.register_agent_handler(PipelineStage.QA, flaky_qa_handler)

    # First attempt fails
    with pytest.raises(RuntimeError) as exc_info:
        pipeline.run_stage(PipelineStage.QA)

    assert "Simulated QA agent connection failure" in str(exc_info.value)
    assert pipeline.state.agent_statuses[PipelineStage.QA] == AgentStatus.FAILED
    assert "qa" in pipeline.state.error_reports

    # Retry stage
    retry_out = pipeline.retry_stage(PipelineStage.QA)
    assert isinstance(retry_out, QAOutput)
    assert pipeline.state.agent_statuses[PipelineStage.QA] == AgentStatus.COMPLETED
    assert "qa" not in pipeline.state.error_reports
