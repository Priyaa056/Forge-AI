"""Database Agent code writer: SQLAlchemy 2.x models, session management and PostgreSQL migrations."""

from datetime import datetime, timezone
from hashlib import sha1
from typing import Dict, List, Tuple

from backend.codegen.blueprint import BEntity, BField, Blueprint
from backend.codegen.project_files import GeneratedProject
from backend.codegen.spec_runtime import entity_rule_config, render_seed_data

AGENT = "db"


def _check_constraints(entity: BEntity) -> List[Tuple[str, str]]:
    checks = []
    for f in entity.fields:
        if f.kind == "enum" and f.enum_values:
            values = ", ".join(f"'{v}'" for v in f.enum_values)
            checks.append((f"ck_{entity.table}_{f.name}_allowed", f"{f.name} IN ({values})"))
        if f.is_numeric and f.min_value is not None:
            checks.append((f"ck_{entity.table}_{f.name}_min", f"{f.name} >= {_num(f.min_value)}"))
        if f.is_numeric and f.max_value is not None:
            checks.append((f"ck_{entity.table}_{f.name}_max", f"{f.name} <= {_num(f.max_value)}"))
    return checks


def _owner_unique_fields(entity: BEntity) -> List[str]:
    """Unique fields of owner-scoped entities are unique per owner (two users may both have a 'Work' category)."""
    if not entity.owner_scoped:
        return []
    return [f.name for f in entity.fields if f.unique and not f.primary_key]


def _column_unique(entity: BEntity, f: BField) -> bool:
    return f.unique and not f.primary_key and f.name not in _owner_unique_fields(entity)


def _num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _on_delete(f: BField) -> str:
    if f.name == "owner_id":
        return "CASCADE"
    return "CASCADE" if f.required else "SET NULL"


def build_db_spec(bp: Blueprint) -> Dict:
    """DBOutput-compatible specification derived from the requirements."""
    tables = []
    upgrade, downgrade = [], []
    for entity in bp.all_entities:
        columns, relationships, indexes = [], [], []
        for f in entity.fields:
            fk = None
            if f.kind == "reference" and f.references:
                target = bp.entity(f.references)
                fk = {"target_table": target.table, "target_column": "id", "on_delete": _on_delete(f), "on_update": "CASCADE"}
                relationships.append({
                    "relationship_name": f.name[:-3] if f.name.endswith("_id") else f.name,
                    "type": "many-to-one", "target_model": target.name, "back_populates": None,
                    "secondary_table": None, "cascade": None,
                })
                indexes.append({"name": f"ix_{entity.table}_{f.name}", "table_name": entity.table, "columns": [f.name],
                                "is_unique": False, "index_type": "btree"})
            check = next((expr for name, expr in _check_constraints(entity) if f" {f.name} " in f" {expr} "), None)
            columns.append({
                "name": f.name,
                "data_type": "SERIAL" if f.primary_key else f.pg_type,
                "is_primary_key": f.primary_key,
                "is_nullable": not f.required and not f.primary_key,
                "is_unique": _column_unique(entity, f),
                "default_value": ("CURRENT_TIMESTAMP" if f.name == "created_at" else (str(f.default) if f.default is not None else None)),
                "foreign_key": fk,
                "check_constraint": check,
            })
            if f.unique and not f.primary_key:
                scoped = f.name in _owner_unique_fields(entity)
                indexes.append({"name": f"uq_{entity.table}_{'owner_' if scoped else ''}{f.name}", "table_name": entity.table,
                                "columns": (["owner_id", f.name] if scoped else [f.name]), "is_unique": True, "index_type": "btree"})
        for child, child_field in bp.children_of(entity.name):
            relationships.append({
                "relationship_name": child.plural_snake, "type": "one-to-many", "target_model": child.name,
                "back_populates": None, "secondary_table": None,
                "cascade": "all, delete-orphan" if child_field.required else None,
            })
        tables.append({
            "table_name": entity.table, "model_name": entity.name, "columns": columns,
            "relationships": relationships, "indexes": indexes, "is_association_table": False,
        })
        upgrade.append(f"CREATE TABLE {entity.table} (...)  -- {len(columns)} columns")
        downgrade.insert(0, f"DROP TABLE IF EXISTS {entity.table}")

    revision = sha1(f"{bp.project_name}:{len(tables)}".encode()).hexdigest()[:12]
    return {
        "project_name": bp.project_name,
        "database_system": "PostgreSQL",
        "tables": tables,
        "sqlalchemy_models_code": render_models(bp),
        "alembic_metadata": {
            "revision_id": revision,
            "down_revision": None,
            "description": f"Initial schema for {bp.project_name}",
            "upgrade_instructions": upgrade,
            "downgrade_instructions": downgrade,
        },
    }


def render_database_module() -> str:
    return '''"""Database engine and session management (generated by FORGE AI Database Agent).

DATABASE_URL selects the database:
  * PostgreSQL (production / docker-compose): postgresql+psycopg2://user:pass@host:5432/dbname
  * SQLite (local preview and tests):        sqlite:///./app.db  (default)
"""

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


DATABASE_URL = _database_url()
_is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables (idempotent). Use migrations/ for managed PostgreSQL deployments."""
    from app import models  # noqa: F401  (registers models on Base.metadata)

    Base.metadata.create_all(bind=engine)
'''


def _mapped_annotation(f: BField) -> str:
    base = {"int": "int", "float": "float", "bool": "bool", "date": "date", "datetime": "datetime", "str": "str"}[f.py_type]
    return base if (f.required or f.primary_key) else f"Optional[{base}]"


def _column_line(entity: BEntity, f: BField, bp: Blueprint) -> str:
    if f.primary_key:
        return "    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)"
    args = []
    kwargs = []
    if f.kind == "reference" and f.references:
        target = bp.entity(f.references)
        args.append(f'ForeignKey("{target.table}.id", ondelete="{_on_delete(f)}")')
        kwargs.append("index=True")
    else:
        args.append(f.sa_type)
    if f.name == "created_at":
        kwargs.append("default=utcnow")
        kwargs.append("nullable=False")
    else:
        kwargs.append(f"nullable={not f.required}")
    if _column_unique(entity, f):
        kwargs.append("unique=True")
        if "index=True" not in kwargs:
            kwargs.append("index=True")
    default = f.python_default_literal()
    if default is not None and f.name != "created_at":
        kwargs.append(f"default={default}")
    annotation = "datetime" if f.name == "created_at" else _mapped_annotation(f)
    return f"    {f.name}: Mapped[{annotation}] = mapped_column({', '.join(args + kwargs)})"


def render_models(bp: Blueprint) -> str:
    lines = [
        '"""SQLAlchemy ORM models (generated by FORGE AI Database Agent from database_schema.json)."""',
        "",
        "from datetime import date, datetime, timezone",
        "from typing import Optional",
        "",
        "from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint",
        "from sqlalchemy.orm import Mapped, mapped_column",
        "",
        "from app.database import Base",
        "",
        "",
        "def utcnow() -> datetime:",
        "    return datetime.now(timezone.utc)",
        "",
    ]
    for entity in bp.all_entities:
        lines.append("")
        lines.append(f"class {entity.name}(Base):")
        doc = entity.description or f"{entity.label} records"
        lines.append(f'    """{doc} (access policy: {entity.access})."""')
        lines.append("")
        lines.append(f'    __tablename__ = "{entity.table}"')
        checks = _check_constraints(entity)
        owner_uniques = _owner_unique_fields(entity)
        if checks or owner_uniques:
            lines.append("    __table_args__ = (")
            for name, expr in checks:
                lines.append(f'        CheckConstraint("{expr}", name="{name}"),')
            for fname in owner_uniques:
                lines.append(f'        UniqueConstraint("owner_id", "{fname}", name="uq_{entity.table}_owner_{fname}"),')
            lines.append("    )")
        lines.append("")
        for f in entity.fields:
            lines.append(_column_line(entity, f, bp))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_migration_sql(bp: Blueprint) -> Tuple[str, str]:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    up = [
        f"-- Migration 001: initial schema for {bp.project_name}",
        f"-- Generated by FORGE AI Database Agent on {stamp}. Target: PostgreSQL 13+.",
        "BEGIN;",
        "",
    ]
    for entity in bp.all_entities:
        cols = []
        for f in entity.fields:
            if f.primary_key:
                cols.append("    id SERIAL PRIMARY KEY")
                continue
            parts = [f"    {f.name} {f.pg_type}"]
            if f.required or f.name == "created_at":
                parts.append("NOT NULL")
            if _column_unique(entity, f):
                parts.append("UNIQUE")
            if f.name == "created_at":
                parts.append("DEFAULT CURRENT_TIMESTAMP")
            elif f.default is not None and f.kind == "boolean":
                parts.append(f"DEFAULT {'TRUE' if str(f.default).lower() == 'true' else 'FALSE'}")
            elif f.default is not None and f.kind == "enum":
                parts.append(f"DEFAULT '{f.default}'")
            elif f.default is not None and f.is_numeric:
                parts.append(f"DEFAULT {f.default}")
            if f.kind == "reference" and f.references:
                target = bp.entity(f.references)
                parts.append(f"REFERENCES {target.table}(id) ON DELETE {_on_delete(f)}")
            cols.append(" ".join(parts))
        for name, expr in _check_constraints(entity):
            cols.append(f"    CONSTRAINT {name} CHECK ({expr})")
        for fname in _owner_unique_fields(entity):
            cols.append(f"    CONSTRAINT uq_{entity.table}_owner_{fname} UNIQUE (owner_id, {fname})")
        up.append(f"CREATE TABLE IF NOT EXISTS {entity.table} (")
        up.append(",\n".join(cols))
        up.append(");")
        for f in entity.fields:
            if f.kind == "reference":
                up.append(f"CREATE INDEX IF NOT EXISTS ix_{entity.table}_{f.name} ON {entity.table} ({f.name});")
        up.append("")
    up.append("COMMIT;")
    down = [f"-- Rollback of migration 001 for {bp.project_name}", "BEGIN;"]
    for entity in reversed(bp.all_entities):
        down.append(f"DROP TABLE IF EXISTS {entity.table} CASCADE;")
    down.append("COMMIT;")
    return "\n".join(up) + "\n", "\n".join(down) + "\n"


def write_db_files(bp: Blueprint, project: GeneratedProject) -> List[str]:
    up_sql, down_sql = render_migration_sql(bp)
    project.write("backend/app/database.py", render_database_module(), AGENT)
    project.write("backend/app/models.py", render_models(bp), AGENT)
    allocations = {e.name: entity_rule_config(bp, e)["allocations"] for e in bp.entities}
    project.write("backend/app/seed_data.py", render_seed_data(bp, {k: v for k, v in allocations.items() if v}), AGENT)
    project.write("backend/migrations/001_initial_schema.sql", up_sql, AGENT)
    project.write("backend/migrations/001_initial_schema.down.sql", down_sql, AGENT)
    project.write("backend/migrations/README.md", (
        "# Database migrations\n\n"
        "Generated by the FORGE AI Database Agent.\n\n"
        "* `001_initial_schema.sql` creates every table, foreign key, CHECK constraint and index (PostgreSQL).\n"
        "* `001_initial_schema.down.sql` reverts it.\n\n"
        "Apply with `psql \"$DATABASE_URL\" -f migrations/001_initial_schema.sql`.\n"
        "The application also calls `Base.metadata.create_all()` on start-up, so local SQLite previews need no manual step.\n"
    ), AGENT)
    return project.files_by_agent(AGENT)
