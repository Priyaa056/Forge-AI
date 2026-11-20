"""Database Agent: designs the relational schema and generates SQLAlchemy models and PostgreSQL migrations.

Inputs: requirements (PM) and the API contract (Backend).
Output: ``database_schema.json`` (DBOutput) + ``backend/app/models.py``, ``database.py`` and ``migrations/``.
The agent verifies that every field the API reads or writes is backed by a column.
"""

from datetime import datetime
from hashlib import sha256
from typing import Any, Dict, List, Optional

from backend.agents.base_agent import BaseAgent
from backend.artifacts.artifact_context import ArtifactContext
from backend.codegen.blueprint import build_blueprint
from backend.codegen.db_writer import build_db_spec, write_db_files
from backend.exceptions import GenerationError, ValidationError
from backend.schemas.backend_schema import BackendOutput
from backend.schemas.db_schema import DBOutput
from backend.schemas.pm_schema import PMOutput

AGENT = "db"


class DBAgent(BaseAgent[DBOutput]):
    """Agent responsible for PostgreSQL relational architecture, SQLAlchemy 2.x models and migrations."""

    stage_name = AGENT

    def __init__(
        self,
        pm_output_path: str = "outputs/pm_output.json",
        backend_output_path: str = "outputs/backend_output.json",
        output_filepath: str = "outputs/db_output.json",
        artifact_context: Optional[ArtifactContext] = None,
        project: Optional[Any] = None,
        log_fn=None,
        previous_requirements: Optional[Dict[str, Any]] = None,
        base_migrations: Optional[List[str]] = None,
    ):
        super().__init__(output_schema_cls=DBOutput, output_filepath=output_filepath,
                         artifact_context=artifact_context, project=project, log_fn=log_fn)
        self.pm_output_path = pm_output_path
        self.backend_output_path = backend_output_path
        self.pm_data: Optional[PMOutput] = None
        self.backend_data: Optional[BackendOutput] = None
        # refinements: the schema of the version being refined (a new migration evolves it in place)
        self.previous_requirements = previous_requirements
        self.base_migrations = base_migrations

    def load_inputs(self) -> None:
        self.pm_data = self.load_upstream("pm", PMOutput, self.pm_output_path)
        self.backend_data = self.load_upstream("backend", BackendOutput, self.backend_output_path)

    @staticmethod
    def generate_revision_id(project_name: str) -> str:
        return sha256(f"{project_name}{datetime.now().isoformat()}".encode()).hexdigest()[:12]

    def generate(self) -> Dict[str, Any]:
        if not self.pm_data or not self.backend_data:
            raise GenerationError("Inputs not loaded. Call load_inputs() first.")
        bp = build_blueprint(self.pm_data)
        spec = build_db_spec(bp)
        columns = {t["model_name"]: {c["name"] for c in t["columns"]} for t in spec["tables"]}
        problems = []
        for ep in self.backend_data.endpoints:
            schema = ep.request_schema
            if not schema or not ep.tags:
                continue
            model = next((e.name for e in bp.entities if e.plural_label in ep.tags), None)
            if model is None:
                continue
            for field in schema.fields:
                if field.name not in columns.get(model, set()):
                    problems.append(f"{ep.method} {ep.path}: field '{field.name}' has no column in {model}")
        if problems:
            raise ValidationError("Schema does not support the API contract: " + "; ".join(sorted(set(problems))[:10]))
        fk_count = sum(1 for t in spec["tables"] for c in t["columns"] if c["foreign_key"])
        check_count = sum(1 for t in spec["tables"] for c in t["columns"] if c["check_constraint"])
        self.log(f"Designed {len(spec['tables'])} tables with {fk_count} foreign keys and {check_count} CHECK constraints; "
                 "API contract fully backed by columns")
        return spec

    def emit_code(self, output: DBOutput) -> List[str]:
        previous = None
        if self.previous_requirements:
            previous = build_blueprint(PMOutput.model_validate(self.previous_requirements))
        title = self.pm_data.change_plan.change_request if self.pm_data.change_plan else ""
        before = set(self.project.manifest)
        files = write_db_files(build_blueprint(self.pm_data), self.project, previous=previous, change_title=title,
                               base_migrations=self.base_migrations)
        added = sorted(p for p in set(self.project.manifest) - before if p.endswith(".sql") and not p.endswith(".down.sql"))
        if previous is not None and added:
            self.log(f"Schema changed: added migration {added[-1].rsplit('/', 1)[-1]} (earlier migrations unchanged)")
        elif previous is not None:
            self.log("No schema change; existing migrations kept")
        return files
