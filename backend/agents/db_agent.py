"""Database Agent for FORGE AI platform."""

import json
from typing import Dict, Any, List, Optional
from pathlib import Path

from backend.agents.base_agent import BaseAgent
from backend.schemas.pm_schema import PMOutput
from backend.schemas.backend_schema import BackendOutput
from backend.schemas.db_schema import DBOutput
from backend.artifacts.artifact_context import ArtifactContext
from backend.exceptions import MissingInputError, ValidationError, GenerationError


class DBAgent(BaseAgent[DBOutput]):
    """Agent responsible for generating PostgreSQL relational architecture, SQLAlchemy 2.x models, and Alembic metadata."""

    def __init__(
        self,
        pm_output_path: str = "outputs/pm_output.json",
        backend_output_path: str = "outputs/backend_output.json",
        output_filepath: str = "outputs/db_output.json",
        artifact_context: Optional[ArtifactContext] = None,
    ):
        super().__init__(
            output_schema_cls=DBOutput,
            output_filepath=output_filepath,
            artifact_context=artifact_context,
        )
        self.pm_output_path = pm_output_path
        self.backend_output_path = backend_output_path
        self.pm_data: Optional[PMOutput] = None
        self.backend_data: Optional[BackendOutput] = None

    def load_inputs(self) -> None:
        """Load and validate PM and Backend specifications."""
        if self.artifact_context:
            self.pm_data = self.artifact_context.get_validated_content("pm", PMOutput)
            self.backend_data = self.artifact_context.get_validated_content("backend", BackendOutput)
        else:
            raw_pm = self.read_json_file(self.pm_output_path)
            try:
                self.pm_data = PMOutput.model_validate(raw_pm)
            except Exception as e:
                raise ValidationError(f"Invalid pm_output.json format: {e}")

            raw_backend = self.read_json_file(self.backend_output_path)
            try:
                self.backend_data = BackendOutput.model_validate(raw_backend)
            except Exception as e:
                raise ValidationError(f"Invalid backend_output.json format: {e}")


    def generate(self) -> Dict[str, Any]:
        """Generate Database specification using LLM or rule-based fallback."""
        if not self.pm_data or not self.backend_data:
            raise GenerationError("Inputs not loaded. Call load_inputs() first.")

        model = self.get_gemini_model()
        if model:
            try:
                prompt = self._build_prompt()
                response = model.generate_content(prompt)
                text = response.text.strip()
                if text.startswith("```json"):
                    text = text[7:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
                parsed = json.loads(text)
                DBOutput.model_validate(parsed)
                return parsed
            except Exception as e:
                self.logger.warning(f"LLM generation failed or returned invalid schema ({e}). Falling back to dynamic rule generator.")

        return self._generate_fallback()

    def _build_prompt(self) -> str:
        """Build structured LLM prompt for database spec generation."""
        return f"""
You are a Senior Database Architect AI and SQLAlchemy 2.x Expert.
Generate a PostgreSQL architecture specification JSON for the following project.

PROJECT NAME: {self.pm_data.project_name}
PM SPEC:
{self.pm_data.model_dump_json(indent=2)}

STRICT RULES:
- Return ONLY valid raw JSON. No markdown formatting.
- Output MUST conform to DBOutput schema.
"""

    def _generate_fallback(self) -> Dict[str, Any]:
        """Dynamic rule-based generator for PostgreSQL schema, SQLAlchemy models, and Alembic metadata."""
        project_name = self.pm_data.project_name
        entities = self.pm_data.database_entities

        entity_table_map = {}
        for entity in entities:
            name = entity.name
            table_name = f"{name.lower()}s" if not name.lower().endswith("s") else name.lower()
            entity_table_map[name] = table_name

        tables: List[Dict[str, Any]] = []
        orm_imports = [
            "from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, func",
            "from sqlalchemy.orm import declarative_base, relationship",
            "from datetime import datetime",
            "",
            "Base = declarative_base()",
            ""
        ]
        orm_classes = []
        upgrade_ops = []
        downgrade_ops = []

        # Map entities to tables
        for entity in entities:
            model_name = entity.name
            table_name = entity_table_map[model_name]

            columns: List[Dict[str, Any]] = []
            relationships: List[Dict[str, Any]] = []
            indexes: List[Dict[str, Any]] = []
            class_lines = [
                f"class {model_name}(Base):",
                f"    __tablename__ = '{table_name}'",
                ""
            ]

            up_cols = []

            for field in entity.fields:
                fname = field.name
                ftype = field.type.upper()

                is_pk = fname == "id" or field.primary_key
                is_unique = field.unique or (fname in ["email", "username"])
                is_nullable = not is_pk and field.nullable

                # Map PostgreSQL data types & SQLAlchemy types
                if "INT" in ftype:
                    pg_type = "INTEGER"
                    sa_type = "Integer"
                elif "DATETIME" in ftype or "TIMESTAMP" in ftype:
                    pg_type = "TIMESTAMP WITH TIME ZONE"
                    sa_type = "DateTime(timezone=True)"
                elif "TEXT" in ftype:
                    pg_type = "TEXT"
                    sa_type = "Text"
                elif "BOOL" in ftype:
                    pg_type = "BOOLEAN"
                    sa_type = "Boolean"
                elif "FLOAT" in ftype or "DECIMAL" in ftype:
                    pg_type = "NUMERIC(10, 2)"
                    sa_type = "Numeric(10, 2)"
                else:
                    pg_type = "VARCHAR(255)"
                    sa_type = "String(255)"

                fk_spec = None
                sa_fk_str = ""
                if fname.endswith("_id") and fname != "id":
                    ref_entity = fname[:-3].capitalize()
                    target_table = entity_table_map.get(ref_entity, f"{fname[:-3]}s")
                    fk_spec = {
                        "target_table": target_table,
                        "target_column": "id",
                        "on_delete": "CASCADE",
                        "on_update": "CASCADE"
                    }
                    sa_fk_str = f", ForeignKey('{target_table}.id', ondelete='CASCADE')"

                    # Add relationship
                    rel_name = ref_entity.lower()
                    relationships.append({
                        "relationship_name": rel_name,
                        "type": "many-to-one",
                        "target_model": ref_entity,
                        "back_populates": table_name,
                        "secondary_table": None,
                        "cascade": None
                    })

                col_dict = {
                    "name": fname,
                    "data_type": pg_type,
                    "is_primary_key": is_pk,
                    "is_nullable": is_nullable,
                    "is_unique": is_unique,
                    "default_value": "autoincrement" if is_pk else ("func.now()" if "DATETIME" in ftype else None),
                    "foreign_key": fk_spec,
                    "check_constraint": None
                }
                columns.append(col_dict)

                # Build ORM line
                sa_kwargs = []
                if is_pk:
                    sa_kwargs.append("primary_key=True, index=True")
                if is_unique and not is_pk:
                    sa_kwargs.append("unique=True")
                if not is_nullable and not is_pk:
                    sa_kwargs.append("nullable=False")
                if "DATETIME" in ftype:
                    sa_kwargs.append("default=func.now()")

                kwargs_str = (", " + ", ".join(sa_kwargs)) if sa_kwargs else ""
                class_lines.append(f"    {fname} = Column({sa_type}{sa_fk_str}{kwargs_str})")

                # Track indexes
                if is_pk or is_unique or fname.endswith("_id"):
                    idx_name = f"idx_{table_name}_{fname}"
                    indexes.append({
                        "name": idx_name,
                        "table_name": table_name,
                        "columns": [fname],
                        "is_unique": is_unique or is_pk,
                        "index_type": "btree"
                    })

                up_cols.append(f"sa.Column('{fname}', sa.{sa_type.split('(')[0]}(), nullable={is_nullable})")

            # Add reverse relationships
            for other_entity in entities:
                if other_entity.name != model_name:
                    for f in other_entity.fields:
                        if f.name == f"{model_name.lower()}_id":
                            other_table = entity_table_map[other_entity.name]
                            relationships.append({
                                "relationship_name": f"{other_entity.name.lower()}s",
                                "type": "one-to-many",
                                "target_model": other_entity.name,
                                "back_populates": model_name.lower(),
                                "secondary_table": None,
                                "cascade": "all, delete-orphan"
                            })
                            class_lines.append(f"    {other_entity.name.lower()}s = relationship('{other_entity.name}', back_populates='{model_name.lower()}', cascade='all, delete-orphan')")

            class_lines.append("")
            orm_classes.append("\n".join(class_lines))

            tables.append({
                "table_name": table_name,
                "model_name": model_name,
                "columns": columns,
                "relationships": relationships,
                "indexes": indexes,
                "is_association_table": False
            })

            upgrade_ops.append(f"op.create_table('{table_name}', {', '.join(up_cols)})")
            downgrade_ops.append(f"op.drop_table('{table_name}')")

        sqlalchemy_models_code = "\n".join(orm_imports) + "\n" + "\n".join(orm_classes)

        alembic_metadata = {
            "revision_id": "0001_initial_schema",
            "down_revision": None,
            "description": f"Initial schema migration for {project_name}",
            "upgrade_instructions": upgrade_ops,
            "downgrade_instructions": downgrade_ops
        }

        return {
            "project_name": project_name,
            "database_system": "PostgreSQL",
            "tables": tables,
            "sqlalchemy_models_code": sqlalchemy_models_code,
            "alembic_metadata": alembic_metadata
        }


if __name__ == "__main__":
    agent = DBAgent()
    agent.run()
