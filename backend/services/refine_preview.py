"""Plan preview for refinements: what a change request would do, before anything is changed.

The PM agent interprets the request against the live version and the result is shown for approval:

* the change plan (changes, agents that update or are reused, what is kept, what cannot be applied);
* warnings about data the change would delete (dropped tables/columns, narrowed values, removed roles);
* the database migration that would be added;
* the exact code changes, computed by running the PM, UI, Backend, Database and Auth agents in a scratch
  copy of the live version (the live version and the project history are not touched).

The approved specification is stored as a draft; applying the draft runs the build with exactly that
specification, so what the user approved is what gets built (even when the PM agent uses an LLM).
"""

import json
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.agents.pm_agent import PMAgent, RefinementNoChange
from backend.artifacts.artifact_manager import ArtifactManager
from backend.artifacts.artifact_store import LocalJsonArtifactStore
from backend.codegen.blueprint import build_blueprint
from backend.codegen.db_writer import MIGRATION_RE
from backend.codegen.migration_diff import render_incremental_migration
from backend.codegen.naming import humanize, pluralize, table_name, to_snake
from backend.monitoring.logger import PipelineLogger
from backend.schemas.pm_schema import DatabaseEntity, PMOutput

DRAFT_TTL_SECONDS = 3600
CODE_STAGES = ("pm", "ui", "backend", "db", "auth")


def _entities(pm: PMOutput) -> Dict[str, DatabaseEntity]:
    return {e.name: e for e in pm.database_entities if not e.is_system}


def _user_fields(e: DatabaseEntity):
    return {f.name: f for f in e.fields if not f.read_only and not f.primary_key and not f.hidden}


def data_warnings(previous: PMOutput, updated: PMOutput) -> List[str]:
    """Consequences for data that already exists in a deployed database."""
    warnings: List[str] = []
    before, after = _entities(previous), _entities(updated)
    for name in before:
        if name not in after:
            plural = humanize(pluralize(to_snake(name))).lower()
            warnings.append(f"All {plural} records will be permanently deleted: the migration drops the "
                            f"{table_name(name)} table.")
    for name, old in before.items():
        new = after.get(name)
        if new is None:
            continue
        of, nf = _user_fields(old), _user_fields(new)
        label = humanize(to_snake(name))
        for fname, f in of.items():
            g = nf.get(fname)
            if g is None:
                warnings.append(f"Values stored in {label} → {f.label or fname} will be deleted (the column is dropped).")
                continue
            if f.type != g.type:
                warnings.append(f"{label} → {g.label or fname} changes from {f.type} to {g.type}; existing values are "
                                "converted and the migration stops if one cannot be.")
            removed = [v for v in f.enum_values if v not in g.enum_values]
            if removed and g.enum_values:
                warnings.append(f"{label} → {g.label or fname} no longer allows {', '.join(removed)}; records using "
                                "these values must be changed before the migration is applied.")
            if f.nullable and not g.nullable:
                warnings.append(f"{label} → {g.label or fname} becomes required; existing records without a value "
                                "must be filled in.")
    roles = {r.name for r in updated.user_roles}
    for r in previous.user_roles:
        if r.name not in roles:
            warnings.append(f"Users with the role '{r.name}' lose their permissions until an administrator assigns "
                            "another role.")
    return warnings


def _base_manifest(base_dir: Path) -> Dict[str, Dict]:
    try:
        return json.loads((Path(base_dir) / "app" / "forge_manifest.json").read_text(encoding="utf-8")).get("files", {})
    except (OSError, ValueError):
        return {}


def migration_preview(previous: PMOutput, updated: PMOutput, base_dir: Path, title: str) -> Optional[Dict[str, str]]:
    migrations = sorted(p for p in _base_manifest(base_dir) if MIGRATION_RE.match(p))
    if not migrations:
        return None
    number = int(MIGRATION_RE.match(migrations[-1]).group(1)) + 1
    rendered = render_incremental_migration(build_blueprint(previous), build_blueprint(updated), number, title)
    if rendered is None:
        return None
    up_sql, _down, slug = rendered
    return {"file": f"backend/migrations/{number:03d}_{slug}.sql", "sql": up_sql}


def file_preview(project_id: str, base: Dict[str, Any], change_request: str,
                 approved: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Run the code-generating agents in a scratch copy of the live version and report the file changes."""
    from backend.services.pipeline import ForgePipeline, PipelineStage

    with tempfile.TemporaryDirectory(prefix="forge-preview-") as tmp:
        root = Path(tmp)
        pipeline = ForgePipeline(
            user_prompt=change_request, project_id=project_id, run_id=f"preview_{uuid.uuid4().hex[:8]}",
            output_dir=str(root / "run"),
            artifact_manager=ArtifactManager(store=LocalJsonArtifactStore(storage_dir=str(root / "artifacts"))),
            pipeline_logger=PipelineLogger(log_dir=str(root / "logs")),
            previous_requirements=base["previous"],
            refine={"base_run_id": base["base_run_id"], "base_version": base["base_version"],
                    "base_dir": str(base["base_dir"]), "change_request": change_request, "approved": approved},
        )
        for stage in CODE_STAGES:
            pipeline.run_stage(PipelineStage(stage))
        return pipeline.file_changes()


def preview_refinement(runs, project_id: str, change_request: str) -> Dict[str, Any]:
    """Interpret ``change_request`` against the live version and return the plan for approval."""
    base = runs.refinement_base(project_id)
    store = runs.store
    previous = PMOutput.model_validate(base["previous"])
    common = {"base_run_id": base["base_run_id"], "base_version": base["base_version"], "change_request": change_request}
    with tempfile.TemporaryDirectory(prefix="forge-plan-") as tmp:
        agent = PMAgent(user_prompt=change_request, previous_requirements=base["previous"],
                        refine={"base_run_id": base["base_run_id"], "base_version": base["base_version"]},
                        output_filepath=str(Path(tmp) / "requirements.json"))
        try:
            updated = agent.run()
        except RefinementNoChange as exc:
            return {**common, "applicable": False, "message": str(exc), "draft_id": None, "plan": None,
                    "warnings": [], "migration": None, "files": None, "notes": []}
    plan = updated.change_plan
    notes: List[str] = []
    approved = updated.model_dump()
    try:
        files = file_preview(project_id, base, change_request, approved)
        notes.append("QA and Deploy also update the generated tests and deployment files during the build.")
    except Exception as exc:  # the preview must never block a refinement; the build reports real problems
        files = None
        notes.append(f"The code changes could not be computed in advance ({type(exc).__name__}); the build will "
                     "report them.")
    now = datetime.now(timezone.utc)
    draft = {**common, "project_id": project_id, "requirements": approved, "created_at": now.isoformat(),
             "expires_at": (now + timedelta(seconds=DRAFT_TTL_SECONDS)).isoformat()}
    draft_id = store.save_draft(project_id, draft, max_age_seconds=DRAFT_TTL_SECONDS)
    return {**common, "applicable": True, "message": None, "draft_id": draft_id, "plan": plan.model_dump(),
            "generation_mode": updated.generation_mode, "warnings": data_warnings(previous, updated),
            "migration": migration_preview(previous, updated, base["base_dir"], change_request),
            "files": files, "notes": notes, "expires_at": draft["expires_at"]}


def draft_is_expired(draft: Dict[str, Any]) -> bool:
    try:
        return datetime.fromisoformat(draft["expires_at"]) < datetime.now(timezone.utc)
    except (KeyError, ValueError):
        return True
