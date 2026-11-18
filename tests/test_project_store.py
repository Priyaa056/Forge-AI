"""Project/run registry, stable-version promotion and file + artifact rollback."""

import pytest

from backend.artifacts.artifact_manager import ArtifactManager
from backend.artifacts.artifact_store import LocalJsonArtifactStore
from backend.codegen.project_files import GeneratedProject
from backend.monitoring.execution_event import EventType
from backend.monitoring.logger import PipelineLogger
from backend.services.project_store import ProjectNotFound, ProjectStore, RollbackRejected

from .conftest import SHOP_PROMPT, TASK_PROMPT


@pytest.fixture
def env(tmp_path, fast_pipeline):
    store = ProjectStore(tmp_path / "projects")
    manager = ArtifactManager(store=LocalJsonArtifactStore(storage_dir=str(tmp_path / "artifacts")))
    logger = PipelineLogger(log_dir=str(tmp_path / "logs"))
    project = store.create_project(TASK_PROMPT)

    def make_run(prompt, marker, **kwargs):
        rid = f"run_{marker}"
        run_dir = store.register_run(project["project_id"], rid, prompt, {})
        pipeline = fast_pipeline(prompt, project_id=project["project_id"], run_id=rid, output_dir=str(run_dir),
                                 artifact_manager=manager, pipeline_logger=logger, **kwargs)
        pipeline.run_pipeline()
        store.save_run_summary(project["project_id"], rid, pipeline.get_status_summary())
        app = GeneratedProject(run_dir / "app")
        app.write("README.md", f"# version {marker}\n", "deploy")
        app.write(f"backend/app/feature_{marker}.py", f"VERSION = '{marker}'\n", "backend")
        app.save_manifest()
        return rid, pipeline.state

    return store, manager, logger, project["project_id"], make_run


def test_promotion_materialises_verified_current_version(env):
    store, _m, _l, pid, make_run = env
    rid, _ = make_run(TASK_PROMPT, "a")
    entry = store.promote(pid, rid)
    assert entry["version"] == 1
    current = store.current_dir(pid)
    assert (current / "README.md").read_text(encoding="utf-8") == "# version a\n"
    project = store.load_project(pid)
    assert project["current_run_id"] == rid and project["current_version"] == 1
    assert store.list_projects()[0]["project_id"] == pid


def test_rollback_restores_files_and_all_artifacts(env):
    store, manager, logger, pid, make_run = env
    rid_a, _ = make_run(TASK_PROMPT, "a")
    store.promote(pid, rid_a)
    rid_b, _ = make_run(SHOP_PROMPT, "b")
    store.promote(pid, rid_b)
    assert (store.current_dir(pid) / "backend/app/feature_b.py").is_file()

    result = store.rollback(pid, rid_a, manager, logger, reason="b broke checkout")
    assert result["status"] == "COMPLETED" and result["new_version"] == 3 and result["restored_from_version"] == 1
    current = store.current_dir(pid)
    assert (current / "backend/app/feature_a.py").is_file()
    assert not (current / "backend/app/feature_b.py").exists()
    for stage, art_id in result["restored_artifacts"].items():
        restored = manager.get_artifact(art_id)
        assert restored.metadata["restored_from_run_id"] == rid_a
        assert restored.version == 3
        assert manager.get_latest_artifact(pid, stage).artifact_id == art_id
    pm = manager.get_artifact(result["restored_artifacts"]["pm"])
    assert "Task" in [e["name"] for e in pm.content["database_entities"]]
    events = [e.event_type for e in logger.read_logs_from_file() if e.project_id == pid]
    assert EventType.ROLLBACK_COMPLETED in events and EventType.VERSION_PROMOTED in events


def test_failed_run_is_never_a_rollback_target(env):
    store, manager, logger, pid, make_run = env
    rid_a, _ = make_run(TASK_PROMPT, "a")
    store.promote(pid, rid_a)
    rid_bad, state = make_run(TASK_PROMPT, "bad", simulate_failure="qa")
    assert state.execution_status.value == "FAILED"
    with pytest.raises(RollbackRejected, match="stable"):
        store.rollback(pid, rid_bad, manager, logger)
    with pytest.raises(RollbackRejected, match="already the active"):
        store.rollback(pid, rid_a, manager, logger)


def test_tampered_snapshot_is_rejected(env):
    store, manager, logger, pid, make_run = env
    rid_a, _ = make_run(TASK_PROMPT, "a")
    store.promote(pid, rid_a)
    rid_b, _ = make_run(SHOP_PROMPT, "b")
    store.promote(pid, rid_b)
    (store.app_dir(pid, rid_a) / "README.md").write_text("tampered", encoding="utf-8")
    with pytest.raises(RollbackRejected, match="integrity"):
        store.rollback(pid, rid_a, manager, logger)
    assert (store.current_dir(pid) / "backend/app/feature_b.py").is_file()  # current untouched
    failures = [e for e in logger.read_logs_from_file() if e.event_type == EventType.ROLLBACK_FAILED]
    assert failures


def test_ids_and_paths_are_validated(env, tmp_path):
    store, *_ = env
    with pytest.raises(ProjectNotFound):
        store.load_project("../etc")
    with pytest.raises(ProjectNotFound):
        store.safe_file(tmp_path, "../outside.txt")
