"""AppBlueprint: a normalized, typed view of the PM requirements that every code writer uses.

The blueprint is built only from the validated PM artifact (``requirements.json``) so the naming
of tables, routes, schema classes and UI routes is identical across the Backend, DB, Auth, UI,
QA and Deploy agents.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backend.codegen.naming import humanize, pluralize, route_segment, slugify, table_name, to_camel, to_snake
from backend.schemas.pm_schema import PMOutput


@dataclass
class BField:
    name: str
    label: str
    kind: str  # string|text|integer|float|decimal|boolean|date|datetime|email|enum|reference
    required: bool = False
    unique: bool = False
    enum_values: List[str] = field(default_factory=list)
    references: Optional[str] = None
    read_only: bool = False
    hidden: bool = False
    searchable: bool = False
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    default: Optional[str] = None
    primary_key: bool = False
    description: Optional[str] = None

    @property
    def py_type(self) -> str:
        return {
            "integer": "int", "reference": "int", "float": "float", "decimal": "float", "boolean": "bool",
            "date": "date", "datetime": "datetime",
        }.get(self.kind, "str")

    @property
    def sa_type(self) -> str:
        return {
            "string": "String(255)", "email": "String(255)", "text": "Text", "integer": "Integer",
            "reference": "Integer", "float": "Float", "decimal": "Numeric(12, 2, asdecimal=False)",
            "boolean": "Boolean", "date": "Date", "datetime": "DateTime(timezone=True)", "enum": "String(50)",
        }[self.kind]

    @property
    def pg_type(self) -> str:
        return {
            "string": "VARCHAR(255)", "email": "VARCHAR(255)", "text": "TEXT", "integer": "INTEGER",
            "reference": "INTEGER", "float": "DOUBLE PRECISION", "decimal": "NUMERIC(12, 2)", "boolean": "BOOLEAN",
            "date": "DATE", "datetime": "TIMESTAMP WITH TIME ZONE", "enum": "VARCHAR(50)",
        }[self.kind]

    @property
    def input_type(self) -> str:
        return {
            "string": "text", "email": "email", "text": "textarea", "integer": "number", "float": "number",
            "decimal": "number", "boolean": "checkbox", "date": "date", "datetime": "datetime-local",
            "enum": "select", "reference": "reference",
        }[self.kind]

    @property
    def is_numeric(self) -> bool:
        return self.kind in ("integer", "float", "decimal")

    def python_default_literal(self) -> Optional[str]:
        if self.default is None:
            return None
        if self.kind == "boolean":
            return "True" if str(self.default).lower() == "true" else "False"
        if self.kind == "enum":
            return repr(self.default)
        if self.is_numeric:
            return str(int(float(self.default))) if self.kind == "integer" else str(float(self.default))
        return None


@dataclass
class BEntity:
    name: str
    snake: str
    plural_snake: str
    table: str
    route: str
    label: str
    plural_label: str
    access: str
    display_field: str
    fields: List[BField]
    is_system: bool = False
    description: str = ""

    @property
    def camel_plural(self) -> str:
        return to_camel(self.plural_snake)

    @property
    def api_path(self) -> str:
        return f"/api/{self.route}"

    @property
    def ui_path(self) -> str:
        return f"/{self.route}"

    @property
    def owner_scoped(self) -> bool:
        return self.access == "owner"

    @property
    def editable_fields(self) -> List[BField]:
        return [f for f in self.fields if not f.read_only and not f.hidden and not f.primary_key]

    @property
    def response_fields(self) -> List[BField]:
        return [f for f in self.fields if not f.hidden]

    @property
    def reference_fields(self) -> List[BField]:
        return [f for f in self.fields if f.kind == "reference" and f.references and f.name != "owner_id"]

    @property
    def enum_fields(self) -> List[BField]:
        return [f for f in self.fields if f.kind == "enum"]

    @property
    def searchable_fields(self) -> List[BField]:
        return [f for f in self.fields if f.searchable and f.kind in ("string", "text", "email") and not f.hidden]

    @property
    def filter_fields(self) -> List[BField]:
        return self.enum_fields + self.reference_fields + [f for f in self.fields if f.kind == "boolean"]

    def permission(self, action: str) -> str:
        return f"{self.plural_snake}:{action}"

    def get_field(self, name: str) -> Optional[BField]:
        return next((f for f in self.fields if f.name == name), None)


@dataclass
class Blueprint:
    project_name: str
    slug: str
    description: str
    app_type: str
    roles: List[str]
    admin_roles: List[str]
    default_role: str
    user: BEntity
    entities: List[BEntity]
    features: List[str]
    has_admin_dashboard: bool = True

    def entity(self, name: str) -> BEntity:
        if name == "User":
            return self.user
        for e in self.entities:
            if e.name == name:
                return e
        raise KeyError(name)

    @property
    def all_entities(self) -> List[BEntity]:
        return [self.user] + self.entities

    def children_of(self, name: str) -> List[tuple]:
        return [(e, f) for e in self.entities for f in e.reference_fields if f.references == name]

    @property
    def primary_entity(self) -> BEntity:
        """The main entity of the app (e.g. Task in a task manager): richest owned entity."""
        return max(
            self.entities,
            key=lambda e: (e.owner_scoped, len(e.reference_fields), len(e.enum_fields), len(e.fields), -self.entities.index(e)),
        )


def _to_bfield(f) -> BField:
    return BField(
        name=f.name,
        label=f.label or humanize(f.name),
        kind=f.type,
        required=not bool(f.nullable),
        unique=bool(f.unique),
        enum_values=list(f.enum_values or []),
        references=f.references,
        read_only=bool(f.read_only),
        hidden=bool(f.hidden),
        searchable=bool(f.searchable),
        min_value=f.min_value,
        max_value=f.max_value,
        default=f.default,
        primary_key=bool(f.primary_key),
        description=f.description,
    )


def _to_bentity(e) -> BEntity:
    snake = to_snake(e.name)
    plural_snake = pluralize(snake)
    return BEntity(
        name=e.name,
        snake=snake,
        plural_snake=plural_snake,
        table=table_name(e.name),
        route=route_segment(e.name),
        label=humanize(e.name),
        plural_label=humanize(plural_snake),
        access=e.access,
        display_field=e.display_field or "id",
        fields=[_to_bfield(f) for f in e.fields],
        is_system=bool(e.is_system),
        description=e.description or "",
    )


def build_blueprint(pm: PMOutput) -> Blueprint:
    """Build the blueprint from a PM output.

    Outputs that were not normalized (e.g. hand-written or legacy ``pm_output.json`` files without the
    system User entity) are normalized first so every downstream agent sees the same conventions.
    """
    if not any(e.is_system or e.name == "User" for e in pm.database_entities):
        from backend.agents.pm_analysis import normalize_requirements

        pm = normalize_requirements(pm)
    user = None
    entities: List[BEntity] = []
    for e in pm.database_entities:
        be = _to_bentity(e)
        if e.name == "User" or e.is_system:
            user = be
        else:
            entities.append(be)
    if user is None:
        raise ValueError("Requirements do not contain the User entity; run normalize_requirements first.")
    if not entities:
        raise ValueError("Requirements contain no application entities.")
    roles = [r.name for r in pm.user_roles] or ["admin", "user"]
    admin_roles = [r.name for r in pm.user_roles if r.is_admin] or ["admin"]
    default_role = next((r for r in roles if r not in admin_roles), roles[-1])
    return Blueprint(
        project_name=pm.project_name,
        slug=slugify(pm.project_name),
        description=pm.description,
        app_type=pm.app_type,
        roles=roles,
        admin_roles=admin_roles,
        default_role=default_role,
        user=user,
        entities=entities,
        features=list(pm.features),
        has_admin_dashboard=pm.has_admin_dashboard,
    )


def entity_ui_config(entity: BEntity, blueprint: Blueprint) -> Dict:
    """JSON-serialisable description of an entity for the generated React pages."""
    fields = []
    for f in entity.response_fields:
        item = {
            "name": f.name, "label": f.label, "type": f.input_type, "kind": f.kind, "required": f.required,
            "readOnly": f.read_only or f.primary_key,
        }
        if f.enum_values:
            item["options"] = [{"value": v, "label": humanize(v)} for v in f.enum_values]
        if f.kind == "reference" and f.references:
            target = blueprint.entity(f.references)
            item["reference"] = {"entity": target.name, "endpoint": target.api_path if target.name != "User" else None,
                                 "labelField": target.display_field}
        if f.min_value is not None:
            item["min"] = f.min_value
        if f.max_value is not None:
            item["max"] = f.max_value
        if f.kind == "decimal":
            item["step"] = "0.01"
        if f.default is not None:
            item["default"] = f.default
        fields.append(item)
    return {
        "name": entity.name,
        "label": entity.label,
        "pluralLabel": entity.plural_label,
        "endpoint": entity.api_path,
        "path": entity.ui_path,
        "access": entity.access,
        "displayField": entity.display_field,
        "searchable": bool(entity.searchable_fields),
        "filters": [f.name for f in entity.filter_fields if f.name != "owner_id"],
        "fields": fields,
    }
