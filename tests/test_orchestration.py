"""Orchestration semantics: ordering, statuses, retries, skips, gates, lineage, monitoring events."""

import pytest

from backend.artifacts.artifact_manager import ArtifactManager
from backend.artifacts.artifact_schema import ArtifactStatus
from backend.artifacts.artifact_store import LocalJsonArtifactStore
from backend.monitoring.execution_event import EventType
from backend.monitoring.logger import PipelineLogger
from backend.schemas.qa_schema import QAOutput
from backend.services.pipeline import STAGE_LINEAGE_DEPENDENCIES, STAGE_ORDER, AgentStatus, PipelineStage

from .conftest import SHOP_PROMPT, TASK_PROMPT


def test_successful_run_completes_all_seven_agents_in_order(fast_pipeline):
    pipeline = fast_pipeline()
    state = pipeline.run_pipeline()
    assert state.execution_status == AgentStatus.COMPLETED
    assert all(status == AgentStatus.COMPLETED for status in state.agent_statuses.values())
    started = [e.agent_name for e in pipeline.pipeline_logger.get_events(state.run_id) if e.event_type == EventType.AGENT_STARTED]
    assert started == [s.value for s in STAGE_ORDER]
    summary = pipeline.get_status_summary()
    assert summary["progress_percent"] == 100 and summary["successful_agent_count"] == 7
    assert (pipeline.specs_dir / "requirements.json").is_file() and (pipeline.specs_dir / "api_spec.json").is_file()


def test_artifacts_record_lineage_and_ids(fast_pipeline):
    pipeline = fast_pipeline()
    state = pipeline.run_pipeline()
    manager = pipeline.artifact_manager
    for stage in STAGE_ORDER:
        art = manager.get_artifact(state.artifact_ids[stage.value])
        assert art.project_id == state.project_id and art.run_id == state.run_id and art.agent_name == stage.value
        assert art.status == ArtifactStatus.COMPLETED and art.version == 1
        expected = {state.artifact_ids[d.value] for d in STAGE_LINEAGE_DEPENDENCIES[stage]}
        assert set(art.input_artifacts) == expected


def test_downstream_agents_use_the_current_runs_outputs(fast_pipeline, tmp_path):
    shared = ArtifactManager(store=LocalJsonArtifactStore(storage_dir=str(tmp_path / "shared_artifacts")))
    first = fast_pipeline(TASK_PROMPT, project_id="proj_same", artifact_manager=shared)
    first.run_pipeline()
    second = fast_pipeline(SHOP_PROMPT, project_id="proj_same", artifact_manager=shared)
    state = second.run_pipeline()
    assert state.execution_status == AgentStatus.COMPLETED
    tables = {t["model_name"] for t in state.agent_outputs["db"]["tables"]}
    assert "Product" in tables and "Task" not in tables  # no stale reuse of the first run's requirements
    assert shared.get_latest_artifact("proj_same", "pm").version == 2


def test_failure_stops_pipeline_and_skips_downstream(fast_pipeline):
    def broken_backend(ctx):
        raise RuntimeError("database connection failed with password=hunter2")

    pipeline = fast_pipeline(handlers={PipelineStage.BACKEND: broken_backend})
    state = pipeline.run_pipeline()
    assert state.execution_status == AgentStatus.FAILED
    assert state.agent_statuses[PipelineStage.UI] == AgentStatus.COMPLETED
    assert state.agent_statuses[PipelineStage.BACKEND] == AgentStatus.FAILED
    for later in (PipelineStage.DB, PipelineStage.AUTH, PipelineStage.QA, PipelineStage.DEPLOY):
        assert state.agent_statuses[later] == AgentStatus.SKIPPED
    assert "hunter2" not in state.error_reports["backend"]
    failed_art = pipeline.artifact_manager.get_artifact(state.artifact_ids["backend"])
    assert failed_art.status == ArtifactStatus.FAILED
    types = [e.event_type for e in pipeline.pipeline_logger.get_events(state.run_id)]
    assert EventType.AGENT_RETRYING in types and EventType.AGENT_FAILED in types
    assert types.count(EventType.AGENT_SKIPPED) == 4 and types[-1] == EventType.PIPELINE_FAILED
    assert state.agent_attempts["backend"] == 2


def test_transient_failure_is_retried_and_recovers(fast_pipeline):
    calls = {"n": 0}
    from tests.conftest import qa_test_double

    def flaky_qa(ctx):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("test runner timed out")
        return qa_test_double(ctx)

    pipeline = fast_pipeline(handlers={PipelineStage.QA: flaky_qa})
    state = pipeline.run_pipeline()
    assert state.execution_status == AgentStatus.COMPLETED
    assert state.agent_attempts["qa"] == 2
    retry_events = [e for e in pipeline.pipeline_logger.get_events(state.run_id) if e.event_type == EventType.AGENT_RETRYING]
    assert len(retry_events) == 1 and retry_events[0].agent_name == "qa"


def test_invalid_prompt_fails_pm_without_retry(fast_pipeline):
    state = fast_pipeline("make app now").run_pipeline()
    assert state.execution_status == AgentStatus.FAILED
    assert state.agent_statuses[PipelineStage.PM] == AgentStatus.FAILED
    assert state.agent_attempts["pm"] == 1
    assert "too short" in state.error_reports["pm"]
    assert all(state.agent_statuses[s] == AgentStatus.SKIPPED for s in STAGE_ORDER[1:])


def test_qa_gate_failure_is_recorded_with_report(fast_pipeline):
    def failing_qa(ctx):
        return QAOutput(status="failed", tests_run=10, tests_passed=7, tests_failed=3,
                        summary="7/10 generated tests passed").model_dump()

    pipeline = fast_pipeline(handlers={PipelineStage.QA: failing_qa})
    state = pipeline.run_pipeline()
    assert state.agent_statuses[PipelineStage.QA] == AgentStatus.FAILED
    assert state.agent_statuses[PipelineStage.DEPLOY] == AgentStatus.SKIPPED
    report = pipeline.artifact_manager.get_artifact(state.artifact_ids["qa"])
    assert report.status == ArtifactStatus.FAILED and report.content["tests_failed"] == 3
    assert "7/10" in state.error_reports["qa"]


def test_simulated_failure_is_labelled_test_mode(fast_pipeline):
    pipeline = fast_pipeline(simulate_failure="db")
    state = pipeline.run_pipeline()
    assert state.agent_statuses[PipelineStage.DB] == AgentStatus.FAILED
    assert "test mode" in state.error_reports["db"]
    assert pipeline.get_status_summary()["simulated_failure"] == "db"


def test_live_updates_are_reported(fast_pipeline):
    seen = []
    pipeline = fast_pipeline(on_update=lambda p: seen.append(p.get_status_summary()["agent_statuses"].copy()))
    pipeline.run_pipeline()
    assert any(s["pm"] == "RUNNING" for s in seen)
    assert any(s["backend"] == "RUNNING" and s["pm"] == "COMPLETED" for s in seen)
    assert seen[-1]["deploy"] == "COMPLETED"


def test_agent_log_events_are_persisted(fast_pipeline, tmp_path):
    logger = PipelineLogger(log_dir=str(tmp_path / "logs"))
    pipeline = fast_pipeline(pipeline_logger=logger)
    pipeline.run_pipeline()
    events = logger.read_logs_from_file()
    assert any(e.event_type == EventType.PIPELINE_COMPLETED for e in events)
    assert all(e.duration_ms is not None for e in events if e.event_type == EventType.AGENT_COMPLETED)


def test_stage_rollback_restores_artifact_version(fast_pipeline, tmp_path):
    shared = ArtifactManager(store=LocalJsonArtifactStore(storage_dir=str(tmp_path / "artifacts_rb")))
    fast_pipeline(TASK_PROMPT, project_id="proj_rb", artifact_manager=shared).run_pipeline()
    second = fast_pipeline(SHOP_PROMPT, project_id="proj_rb", artifact_manager=shared)
    second.run_pipeline()
    result = second.rollback_stage(PipelineStage.DEPLOY, target_version=1, reason="test")
    assert result.status == "COMPLETED" and result.restored_version == 3
    with pytest.raises(Exception):
        second.rollback_stage(PipelineStage.PM, target_version=1)  # downstream artifacts depend on PM
