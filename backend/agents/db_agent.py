"""Database Agent for FORGE AI platform."""

import json
from typing import Dict, Any, List, Optional
from pathlib import Path

from backend.agents.base_agent import BaseAgent
from backend.schemas.pm_schema import PMOutput
from backend.schemas.backend_schema import BackendOutput
from backend.schemas.db_schema import DBOutput
from backend.exceptions import MissingInputError, ValidationError, GenerationError


class DBAgent(BaseAgent[DBOutput]):
    """Agent responsible for generating PostgreSQL relational architecture, SQLAlchemy 2.x models, and Alembic metadata."""

    def __init__(self,
                 pm_output_path: str = "outputs/pm_output.json",
                 backend_output_path: str = "outputs/backend_output.json",
                 output_filepath: str = "outputs/db_output.json"):
        super().__init__(output_schema_cls=DBOutput, output_filepath=output_filepath)
        self.pm_output_path = pm_output_path
        self.backend_output_path = backend_output_path
        self.pm_data: Optional[PMOutput] = None
        self.backend_data: Optional[BackendOutput] = None

    def load_inputs(self) -> None:
        """Load and validate PM and Backend specifications."""
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
        """Generate Database specification using LLM or rule-based fallback.

        Failure modes:
        - LLM API unavailable / network error → falls back to rule-based generator (safe, intended).
        - LLM returns malformed JSON or output that fails the Pydantic schema → raises
          GenerationError so the calling pipeline is explicitly notified (never silently replaced).
        """
        if not self.pm_data or not self.backend_data:
            raise GenerationError("Inputs not loaded. Call load_inputs() first.")

        model = self.get_gemini_model()
        if model:
            # --- Phase 1: LLM API call -------------------------------------------------
            # A network/auth/quota failure is an infrastructure problem; fall back safely.
            llm_text: str | None = None
            try:
                prompt = self._build_prompt()
                response = model.generate_content(prompt)
                llm_text = response.text.strip()
            except Exception as e:
                self.logger.warning(
                    f"LLM API call failed ({e}). Falling back to rule-based generator."
                )

            # --- Phase 2: Output validation --------------------------------------------
            # The LLM responded — validate strictly. Do NOT fall back on bad output;
            # the caller must know the LLM produced unusable data.
            if llm_text is not None:
                return self.parse_and_validate_llm_output(llm_text)

        return self._generate_fallback()

    @staticmethod
    def _infer_check_constraint(field_name: str, field_type: str, description: Optional[str] = None) -> Optional[str]:
        """Derive appropriate SQL CHECK constraint expression from field metadata.

        Returns None if no CHECK constraint is required for the column.
        """
        fname = field_name.lower()
        ftype = field_type.upper()
        desc = (description or "").lower()

        # Check rating/stars
        if "rating" in fname or "stars" in fname:
            return f"{field_name} >= 1 AND {field_name} <= 5"

        # Check non-negative numeric fields (price, quantity, stock, amount, score, count, balance, total)
        if any(k in fname for k in ["price", "quantity", "stock", "amount", "score", "count", "balance", "total_amount"]):
            if any(t in ftype for t in ["INT", "FLOAT", "NUMERIC", "DECIMAL", "DOUBLE", "REAL"]):
                return f"{field_name} >= 0"

        # Check percentage fields
        if "percent" in fname or "percentage" in fname:
            return f"{field_name} >= 0 AND {field_name} <= 100"

        # Check description hints
        if desc:
            if "must be >= 0" in desc or "non-negative" in desc:
                return f"{field_name} >= 0"
            if "between 1 and 5" in desc:
                return f"{field_name} >= 1 AND {field_name} <= 5"

        return None

    @staticmethod
    def generate_revision_id(project_name: str, sequence_num: int = 1) -> str:
        """Generate a dynamic, unique Alembic migration revision ID."""
        import hashlib
        clean_name = "".join(c for c in project_name.lower() if c.isalnum() or c == "_")
        clean_name = clean_name[:16].strip("_") or "app"
        content_hash = hashlib.sha256(f"{project_name}_{sequence_num}".encode("utf-8")).hexdigest()[:8]
        return f"rev_{sequence_num:04d}_{clean_name}_{content_hash}"

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
- Generate appropriate `check_constraint` SQL expressions for columns where business logic requires value validation (e.g., `price >= 0`, `quantity >= 0`, `rating >= 1 AND rating <= 5`). Leave `check_constraint` as null for standard columns.
- Generate a dynamic revision_id in alembic_metadata.
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
        has_any_check = False

        # First pass to check if any field has check constraint for imports
        for entity in entities:
            for field in entity.fields:
                if self._infer_check_constraint(field.name, field.type, getattr(field, "description", None)):
                    has_any_check = True
                    break

        sa_imports = "from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, func"
        if has_any_check:
            sa_imports = "from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, CheckConstraint, func"

        orm_imports = [
            sa_imports,
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
                fdesc = getattr(field, "description", None)

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

                check_constraint = self._infer_check_constraint(fname, ftype, fdesc)

                col_dict = {
                    "name": fname,
                    "data_type": pg_type,
                    "is_primary_key": is_pk,
                    "is_nullable": is_nullable,
                    "is_unique": is_unique,
                    "default_value": "autoincrement" if is_pk else ("func.now()" if "DATETIME" in ftype else None),
                    "foreign_key": fk_spec,
                    "check_constraint": check_constraint
                }
                columns.append(col_dict)

                # Build ORM line
                sa_kwargs = []
                if check_constraint:
                    sa_kwargs.append(f"CheckConstraint('{check_constraint}')")
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

        revision_id = self.generate_revision_id(project_name)
        alembic_metadata = {
            "revision_id": revision_id,
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
