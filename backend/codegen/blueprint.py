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
    kind: str  # string|text|integer|float|decimal|boolean|date|datetime|time|email|enum|reference
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
            "string": "String(255)", "email": "String(255)", "text": "Text", "integer": "Integer", "time": "String(5)",
            "reference": "Integer", "float": "Float", "decimal": "Numeric(12, 2, asdecimal=False)",
            "boolean": "Boolean", "date": "Date", "datetime": "DateTime(timezone=True)", "enum": "String(50)",
        }[self.kind]

    @property
    def pg_type(self) -> str:
        return {
            "string": "VARCHAR(255)", "email": "VARCHAR(255)", "text": "TEXT", "integer": "INTEGER", "time": "VARCHAR(5)",
            "reference": "INTEGER", "float": "DOUBLE PRECISION", "decimal": "NUMERIC(12, 2)", "boolean": "BOOLEAN",
            "date": "DATE", "datetime": "TIMESTAMP WITH TIME ZONE", "enum": "VARCHAR(50)",
        }[self.kind]

    @property
    def input_type(self) -> str:
        return {
            "string": "text", "email": "email", "text": "textarea", "integer": "number", "float": "number",
            "decimal": "number", "boolean": "checkbox", "date": "date", "datetime": "datetime-local", "time": "time",
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
class BModule:
    """A navigation module from the specification (in the user's terminology)."""
    key: str
    name: str
    label: str
    kind: str          # entities | reports
    entities: List[str]
    path: str
    description: str = ""


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
    # dynamic specification (spec_version 2) shared by every agent
    purpose: str = ""
    modules: List[BModule] = field(default_factory=list)
    workflows: Dict[str, Dict] = field(default_factory=dict)          # entity -> WorkflowSpec dict
    rules: List[Dict] = field(default_factory=list)                   # BusinessRule dicts
    metrics: List[Dict] = field(default_factory=list)                 # DashboardMetric dicts
    permissions: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)  # role -> entity -> actions
    theme: Dict[str, str] = field(default_factory=dict)
    seed_records: Dict[str, List[Dict]] = field(default_factory=dict)
    demo_data: bool = False
    ambiguities: List[str] = field(default_factory=list)
    unsupported: List[str] = field(default_factory=list)

    def can(self, role: str, entity: str, action: str) -> bool:
        if role in self.admin_roles:
            return True
        return action in self.permissions.get(role, {}).get(entity, [])

    def rules_for(self, entity: str, kind: Optional[str] = None) -> List[Dict]:
        return [r for r in self.rules if r.get("entity") == entity and (kind is None or r.get("kind") == kind)]

    def module_of(self, entity: str) -> Optional[BModule]:
        return next((m for m in self.modules if entity in m.entities), None)

    @property
    def has_reports(self) -> bool:
        return any(m.kind == "reports" for m in self.modules)

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
    if not pm.module_specs:  # legacy requirements (spec_version 1): derive the dynamic spec from the schema
        from backend.agents.spec_finalize import finalize_spec

        pm = finalize_spec(pm.model_copy(deep=True))
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
    names = {e.name for e in entities}
    permissions = _permission_matrix(pm, roles, admin_roles, entities)
    # self-registered accounts get the least-privileged non-admin role; admins assign the others
    non_admin = [r for r in roles if r not in admin_roles]
    default_role = min(non_admin, key=lambda r: (sum(len([a for a in acts if a != "read"])
                                                     for acts in permissions.get(r, {}).values()),
                                                 non_admin.index(r))) if non_admin else roles[-1]
    modules = _modules(pm, entities)
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
        purpose=pm.purpose or "",
        modules=modules,
        workflows={w.entity: w.model_dump() for w in pm.workflows if w.entity in names and w.transitions},
        rules=[r.model_dump() for r in pm.business_rules if r.entity in names],
        metrics=[m.model_dump() for m in pm.dashboard_metrics if m.kind != "ask" and (m.entity is None or m.entity in names)],
        permissions=permissions,
        theme=dict(pm.theme or {}),
        seed_records={k: v for k, v in (pm.seed_records or {}).items() if k in names},
        demo_data=bool(pm.demo_data),
        ambiguities=list(pm.ambiguities),
        unsupported=list(pm.unsupported_requests),
    )


def _permission_matrix(pm: PMOutput, roles: List[str], admin_roles: List[str],
                       entities: List[BEntity]) -> Dict[str, Dict[str, List[str]]]:
    """role -> entity -> actions; from the spec when present, otherwise from each entity's access policy."""
    matrix: Dict[str, Dict[str, List[str]]] = {r: {} for r in roles}
    explicit = {(p.role, p.entity): sorted(set(p.actions)) for p in pm.role_permissions}
    for role in roles:
        for e in entities:
            if role in admin_roles:
                acts = ["create", "delete", "read", "update"]
            elif (role, e.name) in explicit:
                acts = explicit[(role, e.name)]
            elif e.access == "admin_managed":
                acts = ["read"]
            elif e.access == "shared":
                acts = ["create", "read", "update"]
            else:
                acts = ["create", "delete", "read", "update"]
            if acts and "read" not in acts:
                acts = sorted(set(acts) | {"read"})
            matrix[role][e.name] = acts
    return matrix


def _modules(pm: PMOutput, entities: List[BEntity]) -> List[BModule]:
    names = [e.name for e in entities]
    modules: List[BModule] = []
    used_paths = {"admin", "login", "register", "reports", ""}
    covered = set()
    for m in pm.module_specs:
        if m.kind == "reports":
            continue
        ents = [e for e in m.entities if e in names and e not in covered]
        if not ents:
            continue
        covered.update(ents)
        path = slugify(m.label or m.name or ents[0]) or slugify(ents[0])
        base, n = path, 2
        while path in used_paths:
            path, n = f"{base}-{n}", n + 1
        used_paths.add(path)
        modules.append(BModule(key=m.key, name=m.name, label=m.label or m.name, kind="entities", entities=ents,
                               path=f"/{path}", description=m.description))
    for e in entities:  # every entity is reachable from navigation
        if e.name not in covered:
            path = slugify(e.plural_label)
            while path in used_paths:
                path += "-x"
            used_paths.add(path)
            modules.append(BModule(key=e.snake, name=e.plural_label.capitalize(), label=e.plural_label.capitalize(),
                                   kind="entities", entities=[e.name], path=f"/{path}"))
    if any(m.kind == "reports" for m in pm.module_specs):
        modules.append(BModule(key="reports", name="Reports", label="Reports", kind="reports", entities=[],
                               path="/reports", description="Counts, status breakdowns and monthly trends"))
    return modules


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
