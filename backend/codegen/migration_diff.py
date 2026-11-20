"""Incremental PostgreSQL migrations for refinements.

Compares the previous blueprint with the refined one and renders the SQL that evolves the existing schema:
new tables, dropped tables, added/dropped columns, changed CHECK constraints (enum values, ranges),
nullability, uniqueness and defaults - plus a ``.down.sql`` that reverts it. Earlier migrations are never
rewritten, so a database created from version N can be upgraded to version N+1 in place.
"""

import re
from typing import Dict, List, Optional, Tuple

from backend.codegen.blueprint import BEntity, BField, Blueprint
from backend.codegen.db_writer import (
    _check_constraints,
    _column_unique,
    column_default_sql,
    column_sql,
    create_table_sql,
)


def _slug(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    stop = {"a", "an", "the", "to", "of", "for", "and", "with", "please", "that", "which", "where", "can", "so"}
    words = [w for w in words if w not in stop][:5]
    return "_".join(words)[:48] or "refinement"


def _tables(bp: Blueprint) -> Dict[str, BEntity]:
    return {e.table: e for e in bp.all_entities}


def render_incremental_migration(previous: Blueprint, current: Blueprint, number: int,
                                 title: str = "") -> Optional[Tuple[str, str, str]]:
    """(up_sql, down_sql, slug) or None when the schema did not change."""
    before, after = _tables(previous), _tables(current)
    up: List[str] = []
    down: List[str] = []
    notes: List[str] = []

    # new tables (in dependency order) / dropped tables (dependants first)
    for e in current.all_entities:
        if e.table not in before:
            up += [f"-- new table {e.table} ({e.label})"] + create_table_sql(current, e) + [""]
            down.insert(0, f"DROP TABLE IF EXISTS {e.table} CASCADE;")
    for e in reversed(previous.all_entities):
        if e.table not in after:
            up += [f"-- {e.label} records were removed from the application", f"DROP TABLE IF EXISTS {e.table} CASCADE;", ""]
            down += create_table_sql(previous, e) + [""]
            notes.append(f"dropping table {e.table} deletes its rows; back up the database before applying this migration "
                         "(the .down.sql recreates the table, not the data).")

    for table, new in after.items():
        old = before.get(table)
        if old is None:
            continue
        old_fields = {f.name: f for f in old.fields}
        new_fields = {f.name: f for f in new.fields}
        changes: List[str] = []
        reverts: List[str] = []
        for f in new.fields:
            if f.name in old_fields:
                continue
            definition = column_sql(current, new, f, allow_not_null=False)
            if f.required and column_default_sql(f) is None:
                notes.append(f"{table}.{f.name} is required in the application but added as NULLable here because "
                             "existing rows have no value; fill it in, then add NOT NULL.")
            changes.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {definition};")
            if f.kind == "reference":
                changes.append(f"CREATE INDEX IF NOT EXISTS ix_{table}_{f.name} ON {table} ({f.name});")
            reverts.insert(0, f"ALTER TABLE {table} DROP COLUMN IF EXISTS {f.name};")
        for f in old.fields:
            if f.name in new_fields:
                continue
            notes.append(f"dropping column {table}.{f.name} deletes its values; back up the database first.")
            changes.append(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {f.name};")
            reverts.insert(0, f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column_sql(previous, old, f, allow_not_null=False)};")
        for name, f in new_fields.items():
            o = old_fields.get(name)
            if o is None or f.primary_key:
                continue
            changes_f, reverts_f = _alter_column(table, old, o, new, f)
            changes += changes_f
            reverts = reverts_f + reverts
        old_checks, new_checks = dict(_check_constraints(old)), dict(_check_constraints(new))
        dropped_cols = set(old_fields) - set(new_fields)
        for name in sorted(set(old_checks) | set(new_checks)):
            if old_checks.get(name) == new_checks.get(name):
                continue
            if name in old_checks and not any(f" {c} " in f" {old_checks[name]} " for c in dropped_cols):
                changes.append(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name};")
            if name in new_checks:
                changes.append(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({new_checks[name]});")
                reverts.insert(0, f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name};")
            if name in old_checks:
                reverts.append(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({old_checks[name]});")
        if changes:
            up += [f"-- {new.label} records"] + changes + [""]
            down += reverts + [""]

    if not up:
        return None
    label = title.strip().splitlines()[0][:150] if title.strip() else "refinement"
    head = [f"-- Migration {number:03d}: {label}",
            f"-- Generated by FORGE AI Database Agent for {current.project_name}. Target: PostgreSQL 13+.",
            "-- Evolves the schema of the previous version in place; earlier migrations are unchanged."]
    head += [f"-- NOTE: {n}" for n in notes]
    up_sql = "\n".join(head + ["BEGIN;", ""] + up + ["COMMIT;"]) + "\n"
    down_sql = "\n".join([f"-- Rollback of migration {number:03d}", "BEGIN;", ""] + down + ["COMMIT;"]) + "\n"
    return up_sql, down_sql, _slug(title)


def _alter_column(table: str, old_entity: BEntity, o: BField, new_entity: BEntity, f: BField) -> Tuple[List[str], List[str]]:
    changes, reverts = [], []
    if o.pg_type != f.pg_type:
        changes.append(f"ALTER TABLE {table} ALTER COLUMN {f.name} TYPE {f.pg_type} USING {f.name}::{f.pg_type};")
        reverts.append(f"ALTER TABLE {table} ALTER COLUMN {f.name} TYPE {o.pg_type} USING {f.name}::{o.pg_type};")
    if bool(o.required) != bool(f.required) and f.name != "created_at":
        changes.append(f"ALTER TABLE {table} ALTER COLUMN {f.name} {'SET' if f.required else 'DROP'} NOT NULL;")
        reverts.append(f"ALTER TABLE {table} ALTER COLUMN {f.name} {'SET' if o.required else 'DROP'} NOT NULL;")
    old_default, new_default = column_default_sql(o), column_default_sql(f)
    if old_default != new_default:
        changes.append(f"ALTER TABLE {table} ALTER COLUMN {f.name} " +
                       (f"SET DEFAULT {new_default};" if new_default else "DROP DEFAULT;"))
        reverts.append(f"ALTER TABLE {table} ALTER COLUMN {f.name} " +
                       (f"SET DEFAULT {old_default};" if old_default else "DROP DEFAULT;"))
    was, now = _column_unique(old_entity, o), _column_unique(new_entity, f)
    if was != now:
        name = f"{table}_{f.name}_key"
        if now:
            changes.append(f"ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE ({f.name});")
            reverts.append(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name};")
        else:
            changes.append(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name};")
            reverts.append(f"ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE ({f.name});")
    return changes, reverts
