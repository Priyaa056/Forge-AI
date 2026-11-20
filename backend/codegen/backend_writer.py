"""Backend Agent code writer: FastAPI application, Pydantic schemas and REST routers."""

import json
import re
from typing import Dict, List

from backend.codegen.blueprint import BEntity, BField, Blueprint
from backend.codegen.project_files import GeneratedProject
from backend.codegen.spec_runtime import RULES_PY, entity_rule_config, py_literal, render_dashboard_router as render_metrics_router
from backend.codegen.spec_runtime import render_reports_router

AGENT = "backend"

DELEGATED_PREFIXES = ("/api/auth", "/api/users")  # implemented by the Authentication agent


def endpoint_roles(bp: Blueprint, entity: BEntity, action: str) -> List[str]:
    """Which roles may perform an action: the specification's role permissions (derived from the prompt's role
    descriptions) or, for legacy specifications, the entity's access policy."""
    if bp.permissions:
        return [role for role in bp.roles if bp.can(role, entity.name, action)]
    everyone = list(bp.roles)
    admins = list(bp.admin_roles)
    if entity.access == "admin_managed":
        return everyone if action == "read" else admins
    if entity.access == "shared":
        return admins if action == "delete" else everyone
    return everyone  # owner: row-level scoping restricts non-admins to their own records


# ---------------------------------------------------------------------------------------------
# API specification (api_spec.json)
# ---------------------------------------------------------------------------------------------

def _schema_fields(fields: List[BField], all_optional: bool = False) -> List[Dict]:
    out = []
    for f in fields:
        rules = {}
        if f.kind in ("string", "email"):
            rules["max_length"] = 255
            if f.required:
                rules["min_length"] = 1
        if f.min_value is not None:
            rules["ge"] = f.min_value
        if f.max_value is not None:
            rules["le"] = f.max_value
        if f.enum_values:
            rules["one_of"] = f.enum_values
        if f.kind == "email":
            rules["format"] = "email"
        out.append({
            "name": f.name,
            "type": f.py_type,
            "required": (f.required and not all_optional),
            "default": f.default,
            "validation_rules": rules,
        })
    return out


def build_api_spec(bp: Blueprint) -> Dict:
    endpoints: List[Dict] = []
    services, repositories = [], []
    for e in bp.entities:
        create_schema = {"name": f"{e.name}Create", "fields": _schema_fields(e.editable_fields)}
        update_schema = {"name": f"{e.name}Update", "fields": _schema_fields(e.editable_fields, all_optional=True)}
        out_schema = {"name": f"{e.name}Out", "status_code": 200, "fields": _schema_fields(e.response_fields)}
        page_schema = {"name": f"{e.name}Page", "status_code": 200, "fields": [
            {"name": "items", "type": f"List[{e.name}Out]", "required": True, "default": None, "validation_rules": {}},
            {"name": "total", "type": "int", "required": True, "default": None, "validation_rules": {}},
        ]}
        scope = "owner" if e.owner_scoped else None
        id_param = [{"name": "item_id", "in_location": "path", "param_type": "int", "required": True,
                     "default": None, "description": f"{e.label} ID"}]
        list_params = [
            {"name": "q", "in_location": "query", "param_type": "str", "required": False, "default": None,
             "description": "Free-text search in " + ", ".join(f.name for f in e.searchable_fields)},
            {"name": "sort", "in_location": "query", "param_type": "str", "required": False, "default": "-created_at",
             "description": "Sort field; prefix with '-' for descending"},
            {"name": "skip", "in_location": "query", "param_type": "int", "required": False, "default": 0, "description": "Offset"},
            {"name": "limit", "in_location": "query", "param_type": "int", "required": False, "default": 20, "description": "Page size (max 200)"},
        ] + [
            {"name": f.name, "in_location": "query", "param_type": f.py_type, "required": False, "default": None,
             "description": f"Filter by {f.label.lower()}"} for f in e.filter_fields
        ]
        refs = ", ".join(f"{f.name} -> {f.references}" for f in e.reference_fields)
        common = {"tags": [e.plural_label], "requires_auth": True, "row_level_scope": scope, "is_file_upload": False}
        endpoints += [
            {**common, "path": e.api_path, "method": "GET", "summary": f"List {e.plural_label.lower()}",
             "description": f"Paginated, searchable and filterable list of {e.plural_label.lower()}."
                            + (" Non-admin users only see their own records." if scope else ""),
             "operation_id": f"list_{e.plural_snake}", "required_roles": endpoint_roles(bp, e, "read"),
             "required_permission": e.permission("read"), "request_schema": None, "response_schema": page_schema,
             "parameters": list_params, "business_logic_summary": f"Query {e.table} with search, filters, sorting and pagination."},
            {**common, "path": f"{e.api_path}/{{item_id}}", "method": "GET", "summary": f"Get a {e.label.lower()}",
             "description": f"Fetch one {e.label.lower()} by id (404 if missing or not visible).",
             "operation_id": f"get_{e.snake}", "required_roles": endpoint_roles(bp, e, "read"),
             "required_permission": e.permission("read"), "request_schema": None, "response_schema": out_schema,
             "parameters": id_param, "business_logic_summary": "Load by primary key and apply row-level visibility."},
            {**common, "path": e.api_path, "method": "POST", "summary": f"Create a {e.label.lower()}",
             "description": f"Validate and create a {e.label.lower()}." + (f" References validated: {refs}." if refs else ""),
             "operation_id": f"create_{e.snake}", "required_roles": endpoint_roles(bp, e, "create"),
             "required_permission": e.permission("create"), "request_schema": create_schema,
             "response_schema": {**out_schema, "status_code": 201}, "parameters": [],
             "business_logic_summary": "Validate body, check referenced records exist and are visible, "
                                       + ("set owner_id to the caller, " if scope else "") + "persist."},
            {**common, "path": f"{e.api_path}/{{item_id}}", "method": "PUT", "summary": f"Update a {e.label.lower()}",
             "description": f"Partially update a {e.label.lower()} (only provided fields change).",
             "operation_id": f"update_{e.snake}", "required_roles": endpoint_roles(bp, e, "update"),
             "required_permission": e.permission("update"), "request_schema": update_schema, "response_schema": out_schema,
             "parameters": id_param, "business_logic_summary": "Load visible record, validate changes and references, save."},
            {**common, "path": f"{e.api_path}/{{item_id}}", "method": "DELETE", "summary": f"Delete a {e.label.lower()}",
             "description": f"Delete a {e.label.lower()}; dependent rows follow the foreign-key ON DELETE rules.",
             "operation_id": f"delete_{e.snake}", "required_roles": endpoint_roles(bp, e, "delete"),
             "required_permission": e.permission("delete"), "request_schema": None,
             "response_schema": {"name": "MessageResponse", "status_code": 200, "fields": [
                 {"name": "message", "type": "str", "required": True, "default": None, "validation_rules": {}}]},
             "parameters": id_param, "business_logic_summary": "Load visible record and delete it."},
        ]
        rule_cfg = entity_rule_config(bp, e)
        for action, t in rule_cfg["transitions"].items():
            endpoints.append({
                **common, "path": f"{e.api_path}/{{item_id}}/actions/{action}", "method": "POST",
                "summary": f"{t['label']} a {e.label.lower()}",
                "description": f"Workflow step: {', '.join(t['from']) or 'any state'} -> {t['to']}.",
                "operation_id": f"{action}_{e.snake}", "required_roles": endpoint_roles(bp, e, "update"),
                "required_permission": e.permission("update"), "request_schema": None, "response_schema": out_schema,
                "parameters": id_param, "business_logic_summary": f"Check the current state, set {rule_cfg['workflow_field']} "
                                                                  f"to {t['to']} and apply the business rules.",
            })
        services.append({"name": f"{e.name}Service", "entity": e.name, "methods": [
            {"name": f"list_{e.plural_snake}", "params": ["q", "filters", "sort", "skip", "limit", "user"], "return_type": f"{e.name}Page",
             "description": "Search/filter/paginate with row-level scope"},
            {"name": f"create_{e.snake}", "params": ["payload", "user"], "return_type": e.name, "description": "Validate references and persist"},
        ]})
        repositories.append({"name": f"{e.name}Repository", "entity": e.name, "methods": [
            {"name": "select_scoped", "query_description": f"SELECT * FROM {e.table}" + (" WHERE owner_id = :user (non-admin)" if scope else ""),
             "return_type": f"List[{e.name}]"},
        ]})

    endpoints.append({
        "path": "/api/dashboard/metrics", "method": "GET", "summary": "Dashboard metrics from the specification",
        "description": "; ".join(m["label"] for m in bp.metrics)[:500], "operation_id": "dashboard_metrics",
        "tags": ["Dashboard"], "requires_auth": True, "required_roles": list(bp.roles), "required_permission": "dashboard:read",
        "row_level_scope": "owner", "request_schema": None,
        "response_schema": {"name": "DashboardMetrics", "status_code": 200, "fields": []}, "parameters": [],
        "business_logic_summary": "Evaluate every dashboard metric of the specification on live records.", "is_file_upload": False,
    })
    if bp.has_reports:
        endpoints.append({
            "path": "/api/reports", "method": "GET", "summary": "Reports with date filters",
            "description": "Per-module counts, status breakdowns, monthly trends and money totals.", "operation_id": "reports",
            "tags": ["Reports"], "requires_auth": True, "required_roles": list(bp.roles), "required_permission": "reports:read",
            "row_level_scope": "owner", "request_schema": None,
            "response_schema": {"name": "Reports", "status_code": 200, "fields": []},
            "parameters": [{"name": "date_from", "in_location": "query", "param_type": "date", "required": False, "default": None, "description": "From"},
                           {"name": "date_to", "in_location": "query", "param_type": "date", "required": False, "default": None, "description": "To"}],
            "business_logic_summary": "Aggregate records by date range.", "is_file_upload": False,
        })
    endpoints.append({
        "path": "/api/dashboard/summary", "method": "GET", "summary": "Dashboard summary for the signed-in user",
        "description": "Record counts per entity visible to the caller.", "operation_id": "dashboard_summary",
        "tags": ["Dashboard"], "requires_auth": True, "required_roles": list(bp.roles), "required_permission": "dashboard:read",
        "row_level_scope": "owner", "request_schema": None,
        "response_schema": {"name": "DashboardSummary", "status_code": 200, "fields": []}, "parameters": [],
        "business_logic_summary": "Count visible records per entity.", "is_file_upload": False,
    })
    if bp.has_admin_dashboard:
        endpoints.append({
            "path": "/api/admin/stats", "method": "GET", "summary": "Admin statistics",
            "description": "Totals per entity, users per role, status breakdowns and recent activity.",
            "operation_id": "admin_stats", "tags": ["Admin"], "requires_auth": True, "required_roles": list(bp.admin_roles),
            "required_permission": "admin:dashboard", "row_level_scope": None, "request_schema": None,
            "response_schema": {"name": "AdminStats", "status_code": 200, "fields": []}, "parameters": [],
            "business_logic_summary": "Aggregate counts across all records.", "is_file_upload": False,
        })
    return {
        "project_name": bp.project_name,
        "architecture": "Layered FastAPI (router -> validation/policy -> SQLAlchemy ORM)",
        "base_url": "/api",
        "endpoints": endpoints,
        "service_layer": services,
        "repository_layer": repositories,
        "global_dependencies": ["get_db", "require_permission", "is_admin"],
        "error_handlers": [
            {"status_code": 401, "exception_type": "HTTPException", "detail": "Not authenticated / invalid token"},
            {"status_code": 403, "exception_type": "HTTPException", "detail": "Role lacks permission"},
            {"status_code": 404, "exception_type": "HTTPException", "detail": "Record not found or not visible"},
            {"status_code": 409, "exception_type": "IntegrityError", "detail": "Duplicate value or invalid reference"},
            {"status_code": 422, "exception_type": "RequestValidationError", "detail": "Invalid input"},
        ],
    }


def check_ui_contract(api_spec: Dict, ui_requirements: List[Dict]) -> Dict:
    """Verify every API call the UI agent planned is implemented (or delegated to the Auth agent)."""
    implemented = {(ep["method"].upper(), _norm(ep["path"])) for ep in api_spec["endpoints"]}
    missing, delegated, covered = [], [], []
    for req in ui_requirements or []:
        method = str(req.get("method", "GET")).upper()
        path = _norm(str(req.get("endpoint", "")))
        if path.startswith(DELEGATED_PREFIXES):
            delegated.append(f"{method} {path}")
        elif (method, path) in implemented:
            covered.append(f"{method} {path}")
        else:
            missing.append(f"{method} {path}")
    return {"covered": covered, "delegated_to_auth": delegated, "missing": missing}


def _norm(path: str) -> str:
    path = re.sub(r"\{[^}]+\}", "{id}", path.split("?")[0].rstrip("/"))
    return path or "/"


# ---------------------------------------------------------------------------------------------
# Code rendering
# ---------------------------------------------------------------------------------------------

def _create_annotation(f: BField) -> str:
    if f.kind == "enum":
        literal = "Literal[" + ", ".join(repr(v) for v in f.enum_values) + "]"
        if f.required:
            default = repr(f.default) if f.default is not None else "..."
            return f"{literal} = {default}"
        return f"Optional[{literal}] = None"
    py = f.py_type
    constraints = _constraints(f)
    if f.required:
        default = f.python_default_literal()
        if f.kind == "boolean":
            return f"bool = {default or 'False'}"
        if default is not None:
            return f"{py} = Field({default}{constraints})"
        return f"{py} = Field(...{constraints})"
    if f.kind == "boolean":
        return f"Optional[bool] = {f.python_default_literal() or 'None'}"
    default = f.python_default_literal() or "None"
    return f"Optional[{py}] = Field({default}{constraints})"


def _update_annotation(f: BField) -> str:
    if f.kind == "enum":
        return "Optional[Literal[" + ", ".join(repr(v) for v in f.enum_values) + "]] = None"
    if f.kind == "boolean":
        return "Optional[bool] = None"
    return f"Optional[{f.py_type}] = Field(None{_constraints(f)})"


def _constraints(f: BField) -> str:
    parts = []
    if f.kind in ("string", "email"):
        parts.append("max_length=255")
        if f.required:
            parts.append("min_length=1")
    if f.kind == "text":
        parts.append("max_length=20000")
    if f.kind == "email":
        parts.append("pattern=EMAIL_PATTERN")
    if f.kind == "time":
        parts.append("pattern=TIME_PATTERN")
    if f.is_numeric and f.min_value is not None:
        parts.append(f"ge={f.min_value if f.kind != 'integer' else int(f.min_value)}")
    if f.is_numeric and f.max_value is not None:
        parts.append(f"le={f.max_value if f.kind != 'integer' else int(f.max_value)}")
    return (", " + ", ".join(parts)) if parts else ""


def _out_annotation(f: BField) -> str:
    py = f.py_type
    if f.primary_key:
        return "int"
    return f"Optional[{py}] = None"


def render_schemas(bp: Blueprint) -> str:
    lines = [
        '"""Pydantic request/response schemas (generated by FORGE AI Backend Agent from api_spec.json)."""',
        "",
        "from datetime import date, datetime",
        "from typing import Any, Dict, List, Literal, Optional",
        "",
        "from pydantic import BaseModel, ConfigDict, Field",
        "",
        r'EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"',
        r'TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"',
        "",
        "",
        "class MessageResponse(BaseModel):",
        "    message: str",
        "",
    ]
    for e in bp.entities:
        editable = e.editable_fields
        lines += ["", f"class {e.name}Create(BaseModel):", f'    """Payload to create a {e.label.lower()}."""', ""]
        for f in editable:
            lines.append(f"    {f.name}: {_create_annotation(f)}")
        if not editable:
            lines.append("    pass")
        lines += ["", "", f"class {e.name}Update(BaseModel):", f'    """Partial update for a {e.label.lower()} (omitted fields are unchanged)."""', ""]
        for f in editable:
            lines.append(f"    {f.name}: {_update_annotation(f)}")
        if not editable:
            lines.append("    pass")
        lines += ["", "", f"class {e.name}Out(BaseModel):", "    model_config = ConfigDict(from_attributes=True)", ""]
        for f in e.response_fields:
            lines.append(f"    {f.name}: {_out_annotation(f)}")
        lines += ["", "", f"class {e.name}Page(BaseModel):", f"    items: List[{e.name}Out]", "    total: int",
                  "    skip: int", "    limit: int", ""]
    lines += ["", "class DashboardSummary(BaseModel):", "    counts: Dict[str, int]", "    role: str", ""]
    return "\n".join(lines).rstrip() + "\n"


def render_entity_router(bp: Blueprint, e: BEntity) -> str:
    cfg = entity_rule_config(bp, e)
    ref_models = sorted({f.references for f in e.reference_fields})
    resource_models = sorted({a["resource"] for a in cfg["allocations"]})
    model_imports = sorted({e.name, "User", *ref_models, *resource_models})
    snapshot_fields = [f.name for f in e.response_fields]
    search_cols = ", ".join(f"{e.name}.{f.name}" for f in e.searchable_fields)
    sortable = [f for f in e.response_fields if f.kind not in ("text",)]
    sort_map = ", ".join(f'"{f.name}": {e.name}.{f.name}' for f in sortable)
    required = sorted(f.name for f in e.editable_fields if f.required)
    references = ", ".join(
        f'"{f.name}": ({f.references}, {bp.entity(f.references).owner_scoped})' for f in e.reference_fields
    )
    filter_params = []
    filter_clauses = []
    for f in e.filter_fields:
        py = "int" if f.kind == "reference" else ("bool" if f.kind == "boolean" else "str")
        filter_params.append(f'    f_{f.name}: Optional[{py}] = Query(None, alias="{f.name}", description="Filter by {f.label.lower()}"),')
        filter_clauses.append(f"    if f_{f.name} is not None:\n        stmt = stmt.where({e.name}.{f.name} == f_{f.name})")

    perm = e.permission
    lines = [
        f'"""REST API for {e.plural_label} (generated by FORGE AI Backend Agent from api_spec.json).',
        "",
        f"Access policy: {e.access}."
        + (" Non-admin users only see and modify their own records." if e.owner_scoped else ""),
        '"""',
        "",
        "from typing import Optional",
        "",
        "from fastapi import APIRouter, Depends, HTTPException, Query",
        "from sqlalchemy import func, or_, select",
        "from sqlalchemy.exc import IntegrityError",
        "from sqlalchemy.orm import Session",
        "",
        "from app.database import get_db",
        f"from app.models import {', '.join(model_imports)}",
        f"from app.schemas import MessageResponse, {e.name}Create, {e.name}Out, {e.name}Page, {e.name}Update",
        "from app.rules import apply_allocations, apply_computed, check_date_order, check_unique_together, snapshot, stamp_transition_dates",
        "from app.security import is_admin, require_permission",
        "",
        f'router = APIRouter(prefix="{e.api_path}", tags=["{e.plural_label}"])',
        "",
        "# Business rules and workflow from the application specification",
        f"DATE_ORDER = {py_literal(cfg['date_order'])}",
        f"COMPUTED = {py_literal(cfg['computed'])}",
        f"UNIQUE_TOGETHER = {py_literal(cfg['unique'])}",
        f"ALLOCATIONS = {py_literal(cfg['allocations'])}",
        f"RESOURCE_MODELS = {{{', '.join(f'{chr(34)}{m}{chr(34)}: {m}' for m in resource_models)}}}",
        f"WORKFLOW_FIELD = {json.dumps(cfg['workflow_field'])}",
        f"TRANSITIONS = {py_literal(cfg['transitions'])}",
        f"SNAPSHOT_FIELDS = {json.dumps(snapshot_fields)}",
        "",
        f"OWNER_SCOPED = {e.owner_scoped}",
        f"SEARCH_COLUMNS = ({search_cols}{',' if search_cols and ',' not in search_cols else ''})" if search_cols else "SEARCH_COLUMNS = ()",
        f"SORT_COLUMNS = {{{sort_map}}}",
        f"REQUIRED_FIELDS = {set(required) if required else 'set()'}",
        f"REFERENCES = {{{references}}}  # field -> (model, target is owner-scoped)",
        "",
        "",
        "def _scoped(stmt, user: User):",
        "    if OWNER_SCOPED and not is_admin(user):",
        f"        stmt = stmt.where({e.name}.owner_id == user.id)" if e.owner_scoped else "        pass",
        "    return stmt",
        "",
        "",
        f"def _get_visible(db: Session, item_id: int, user: User) -> {e.name}:",
        f"    obj = db.get({e.name}, item_id)",
        "    if obj is None or (OWNER_SCOPED and not is_admin(user) and getattr(obj, \"owner_id\", None) != user.id):",
        f'        raise HTTPException(status_code=404, detail="{e.label} not found")',
        "    return obj",
        "",
        "",
        "def _check_references(db: Session, data: dict, user: User) -> None:",
        "    for field, (model, scoped) in REFERENCES.items():",
        "        value = data.get(field)",
        "        if value is None:",
        "            continue",
        "        target = db.get(model, value)",
        "        if target is None or (scoped and not is_admin(user) and getattr(target, \"owner_id\", None) != user.id):",
        '            raise HTTPException(status_code=422, detail=f"{field}: {model.__name__} {value} does not exist")',
        "",
        "",
        f"def _enforce(db: Session, obj: {e.name}, before) -> None:",
        "    apply_computed(obj, COMPUTED)",
        "    check_date_order(obj, DATE_ORDER)",
        f"    check_unique_together(db, {e.name}, obj, UNIQUE_TOGETHER)",
        "    apply_allocations(db, before, snapshot(obj, SNAPSHOT_FIELDS), ALLOCATIONS, RESOURCE_MODELS)",
        "",
        "",
        "def _commit(db: Session) -> None:",
        "    try:",
        "        db.commit()",
        "    except IntegrityError as exc:",
        "        db.rollback()",
        "        raise HTTPException(",
        "            status_code=409,",
        '            detail="The request conflicts with existing data (duplicate unique value or invalid reference).",',
        "        ) from exc",
        "",
        "",
        f'@router.get("", response_model={e.name}Page, summary="List {e.plural_label.lower()}")',
        f"def list_{e.plural_snake}(",
        '    q: Optional[str] = Query(None, description="Free-text search"),',
        *filter_params,
        '    sort: str = Query("-created_at", description="Sort field, prefix with - for descending"),',
        "    skip: int = Query(0, ge=0),",
        "    limit: int = Query(20, ge=1, le=200),",
        "    db: Session = Depends(get_db),",
        f'    user: User = Depends(require_permission("{perm("read")}")),',
        "):",
        f"    stmt = _scoped(select({e.name}), user)",
        "    if q and SEARCH_COLUMNS:",
        '        pattern = f"%{q.strip()}%"',
        "        stmt = stmt.where(or_(*[column.ilike(pattern) for column in SEARCH_COLUMNS]))",
        *filter_clauses,
        "    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0",
        f'    column = SORT_COLUMNS.get(sort.lstrip("-"), {e.name}.created_at)',
        f'    stmt = stmt.order_by(column.desc() if sort.startswith("-") else column.asc(), {e.name}.id.desc())',
        "    items = db.scalars(stmt.offset(skip).limit(limit)).all()",
        f"    return {e.name}Page(items=items, total=total, skip=skip, limit=limit)",
        "",
        "",
        f'@router.get("/{{item_id}}", response_model={e.name}Out, summary="Get a {e.label.lower()}")',
        f'def get_{e.snake}(item_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("{perm("read")}"))):',
        "    return _get_visible(db, item_id, user)",
        "",
        "",
        f'@router.post("", response_model={e.name}Out, status_code=201, summary="Create a {e.label.lower()}")',
        f"def create_{e.snake}(",
        f"    payload: {e.name}Create,",
        "    db: Session = Depends(get_db),",
        f'    user: User = Depends(require_permission("{perm("create")}")),',
        "):",
        "    data = payload.model_dump()",
        "    _check_references(db, data, user)",
        f"    obj = {e.name}(**data)",
        "    _enforce(db, obj, None)",
    ]
    if e.owner_scoped:
        lines.append("    obj.owner_id = user.id")
    lines += [
        "    db.add(obj)",
        "    _commit(db)",
        "    db.refresh(obj)",
        "    return obj",
        "",
        "",
        f'@router.put("/{{item_id}}", response_model={e.name}Out, summary="Update a {e.label.lower()}")',
        f'@router.patch("/{{item_id}}", response_model={e.name}Out, include_in_schema=False)',
        f"def update_{e.snake}(",
        "    item_id: int,",
        f"    payload: {e.name}Update,",
        "    db: Session = Depends(get_db),",
        f'    user: User = Depends(require_permission("{perm("update")}")),',
        "):",
        "    obj = _get_visible(db, item_id, user)",
        "    before = snapshot(obj, SNAPSHOT_FIELDS)",
        "    data = payload.model_dump(exclude_unset=True)",
        "    for field in REQUIRED_FIELDS:",
        "        if field in data and data[field] is None:",
        '            raise HTTPException(status_code=422, detail=f"{field} cannot be empty")',
        "    _check_references(db, data, user)",
        "    for field, value in data.items():",
        "        setattr(obj, field, value)",
        "    _enforce(db, obj, before)",
        "    _commit(db)",
        "    db.refresh(obj)",
        "    return obj",
        "",
        "",
        f'@router.delete("/{{item_id}}", response_model=MessageResponse, summary="Delete a {e.label.lower()}")',
        f'def delete_{e.snake}(item_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("{perm("delete")}"))):',
        "    obj = _get_visible(db, item_id, user)",
        "    apply_allocations(db, snapshot(obj, SNAPSHOT_FIELDS), None, ALLOCATIONS, RESOURCE_MODELS)",
        "    db.delete(obj)",
        "    _commit(db)",
        f'    return MessageResponse(message=f"{e.label} {{item_id}} deleted")',
        "",
    ]
    if cfg["transitions"]:
        lines += [
            "",
            f'@router.post("/{{item_id}}/actions/{{action}}", response_model={e.name}Out, summary="Run a workflow action")',
            f"def run_{e.snake}_action(",
            "    item_id: int,",
            "    action: str,",
            "    db: Session = Depends(get_db),",
            f'    user: User = Depends(require_permission("{perm("update")}")),',
            "):",
            "    transition = TRANSITIONS.get(action)",
            "    if transition is None:",
            "        raise HTTPException(status_code=404, detail=f\"Unknown action '{action}'\")",
            "    obj = _get_visible(db, item_id, user)",
            "    current = getattr(obj, WORKFLOW_FIELD)",
            '    if transition["from"] and current not in transition["from"]:',
            "        state = str(current).replace('_', ' ')",
            "        verb = transition['label'].lower()",
            f'        raise HTTPException(status_code=409, detail=f"Cannot {{verb}} this {e.label.lower()} because it is {{state}}.")',
            "    before = snapshot(obj, SNAPSHOT_FIELDS)",
            '    setattr(obj, WORKFLOW_FIELD, transition["to"])',
            '    stamp_transition_dates(obj, transition["dates"])',
            "    _enforce(db, obj, before)",
            "    _commit(db)",
            "    db.refresh(obj)",
            "    return obj",
            "",
        ]
    return "\n".join(lines)


def render_main(bp: Blueprint) -> str:
    router_modules = ["auth", "users", "dashboard"] + (["reports"] if bp.has_reports else []) + [f"{e.plural_snake}" for e in bp.entities]
    imports = ", ".join(router_modules)
    includes = "\n".join(f"app.include_router({m}.router)" for m in router_modules)
    return f'''"""{bp.project_name} API (generated by FORGE AI Backend Agent).

Run locally:  uvicorn app.main:app --reload --port 8000   (from the backend/ directory)
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.database import engine, init_db
from app.routers import {imports}
from app.seed import seed_admin
from app.seed_data import seed_demo_data, seed_reference_data

PROJECT_NAME = {json.dumps(bp.project_name)}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    seed_admin()
    seed_reference_data()
    seed_demo_data()
    yield


app = FastAPI(
    title=PROJECT_NAME,
    version="1.0.0",
    description={json.dumps((bp.purpose or bp.description)[:500])},
    lifespan=lifespan,
)

_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])

{includes}


@app.get("/health", tags=["Health"])
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # pragma: no cover - reported to the caller
        database = "unavailable"
    return {{"status": "healthy" if database == "ok" else "degraded", "database": database, "app": PROJECT_NAME}}


@app.get("/api", tags=["Health"])
def api_root():
    return {{"name": PROJECT_NAME, "docs": "/docs", "health": "/health"}}


FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist")).resolve()

if FRONTEND_DIST.is_dir():
    if (FRONTEND_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{{full_path:path}}", include_in_schema=False)
    def serve_frontend(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIST in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
'''


def render_requirements() -> str:
    return "\n".join([
        "fastapi>=0.110",
        "uvicorn>=0.27",
        "sqlalchemy>=2.0",
        "pydantic>=2.5",
        "psycopg2-binary>=2.9",
        "httpx>=0.27",
        "pytest>=8.0",
    ])


def write_backend_files(bp: Blueprint, project: GeneratedProject) -> List[str]:
    project.write("backend/app/__init__.py", f'"""{bp.project_name} backend package."""\n', AGENT)
    project.write("backend/app/routers/__init__.py", '"""API routers."""\n', AGENT)
    project.write("backend/app/schemas.py", render_schemas(bp), AGENT)
    project.write("backend/app/main.py", render_main(bp), AGENT)
    project.write("backend/app/rules.py", RULES_PY, AGENT)
    project.write("backend/app/routers/dashboard.py", render_metrics_router(bp), AGENT)
    if bp.has_reports:
        project.write("backend/app/routers/reports.py", render_reports_router(bp), AGENT)
    for e in bp.entities:
        project.write(f"backend/app/routers/{e.plural_snake}.py", render_entity_router(bp, e), AGENT)
    project.write("backend/requirements.txt", render_requirements(), AGENT)
    return project.files_by_agent(AGENT)
