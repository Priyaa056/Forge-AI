"""Requirement analysis for the PM Agent.

* :func:`analyze_prompt` - deterministic, prompt-driven specification (``spec_extraction``) followed by
  normalization and finalization. Every module/entity comes from the prompt; there is no fixed
  catalogue of applications, domains or default entity sets.
* :func:`normalize_requirements` - enforces the naming and structural conventions every downstream
  agent relies on (also applied to LLM output).
* :func:`finalize_spec` (re-exported) - resolves workflows, rules, metrics and seeds on the final schema.
"""

import re
from typing import Dict, List

from backend.agents.spec_extraction import PromptValidationError, extract_spec, validate_prompt
from backend.agents.spec_finalize import finalize_spec
from backend.codegen.naming import fk_field_name, humanize, pluralize, safe_identifier, singularize, to_pascal, to_snake
from backend.schemas.pm_schema import (
    DatabaseEntity,
    DevelopmentTask,
    EntityField,
    ModuleSpec,
    PMOutput,
    Requirement,
    RolePermission,
    TechStack,
    UserRole,
)

MAX_ENTITIES = 25

__all__ = ["PromptValidationError", "analyze_prompt", "finalize_spec", "normalize_requirements", "validate_prompt"]


def analyze_prompt(prompt: str) -> PMOutput:
    """Derive structured, prompt-specific requirements without an LLM."""
    return finalize_spec(normalize_requirements(extract_spec(prompt)))


# ---------------------------------------------------------------------------------------------
# Normalization (applies to both LLM and deterministic output)
# ---------------------------------------------------------------------------------------------

_TYPE_ALIASES = {
    "str": "string", "string": "string", "varchar": "string", "char": "string", "url": "string", "phone": "string",
    "text": "text", "longtext": "text", "markdown": "text",
    "int": "integer", "integer": "integer", "bigint": "integer", "smallint": "integer", "number": "integer",
    "float": "float", "double": "float", "real": "float",
    "decimal": "decimal", "numeric": "decimal", "money": "decimal", "currency": "decimal", "price": "decimal",
    "bool": "boolean", "boolean": "boolean",
    "date": "date",
    "datetime": "datetime", "timestamp": "datetime", "timestamptz": "datetime",
    "time": "time",
    "email": "email",
    "enum": "enum", "choice": "enum", "select": "enum",
    "reference": "reference", "foreign_key": "reference", "fk": "reference", "relation": "reference",
}


def _normalize_type(raw: str) -> str:
    t = (raw or "string").strip().lower()
    t = re.sub(r"\(.*\)", "", t).strip()
    t = t.replace("timestamp with time zone", "datetime")
    if t in _TYPE_ALIASES:
        return _TYPE_ALIASES[t]
    for key, value in _TYPE_ALIASES.items():
        if key in t:
            return value
    return "string"


def _user_entity(roles: List[UserRole]) -> DatabaseEntity:
    role_names = [r.name for r in roles] or ["admin", "user"]
    non_admin = [r.name for r in roles if not r.is_admin] or ["user"]
    return DatabaseEntity(
        name="User",
        description="Application user account (managed by the Authentication agent)",
        is_system=True,
        access="admin_managed",
        display_field="full_name",
        fields=[
            EntityField(name="id", type="integer", primary_key=True, nullable=False, read_only=True, label="ID"),
            EntityField(name="email", type="email", unique=True, nullable=False, searchable=True, label="Email"),
            EntityField(name="full_name", type="string", nullable=False, searchable=True, label="Full name"),
            EntityField(name="role", type="enum", enum_values=role_names, default=non_admin[0], nullable=False, label="Role"),
            EntityField(name="is_active", type="boolean", default="true", nullable=False, label="Active"),
            EntityField(name="hashed_password", type="string", nullable=False, hidden=True, read_only=True, label="Password hash"),
            EntityField(name="created_at", type="datetime", read_only=True, label="Created at"),
        ],
    )


def _links_to_owner(f) -> bool:
    """A field linking to app 'Owner' records (not the owner_id -> User ownership column)."""
    target = to_pascal(singularize(f.references)) if f.references else ""
    return target == "Owner" or (safe_identifier(f.name) in ("owner", "owner_id") and target != "User")


def _owner_alias(entities: List[DatabaseEntity]) -> str:
    """New name for an app entity called 'Owner' that other records link to ('' when no rename is needed).

    Such a link would be called owner_id, the column that records which user owns a row. The first linking
    entity gives the prefix ("pets -> owners" -> PetOwner). An Owner nothing links to keeps its name, so
    existing projects are not renamed.
    """
    if not any(e.name and to_pascal(singularize(e.name)) == "Owner" for e in entities):
        return ""
    taken = {to_pascal(singularize(e.name)) for e in entities if e.name}
    linking = [to_pascal(singularize(e.name)) for e in entities if e.name and to_pascal(singularize(e.name))
               not in ("Owner", "User") and any(_links_to_owner(f) for f in e.fields)]
    if not linking:
        return ""
    for name in linking:
        if f"{name}Owner" not in taken:
            return f"{name}Owner"
    return "OwnerProfile" if "OwnerProfile" not in taken else "OwnerRecord"


def normalize_requirements(pm: PMOutput) -> PMOutput:
    """Enforce conventions every downstream agent depends on. Raises PromptValidationError if unusable."""
    data = pm.model_copy(deep=True)

    # Roles
    roles: List[UserRole] = []
    seen_roles = set()
    for role in data.user_roles or []:
        name = to_snake(role.name)
        if name == "administrator":
            name = "admin"
        if not name or name in seen_roles:
            continue
        seen_roles.add(name)
        roles.append(UserRole(name=name, description=role.description, is_admin=role.is_admin or name == "admin"))
    if "admin" not in seen_roles:
        roles.insert(0, UserRole(name="admin", description="Full administrative access", is_admin=True))
    if not any(not r.is_admin for r in roles):
        roles.append(UserRole(name="user", description="Registered user"))
    data.user_roles = roles

    # Entities
    entities: List[DatabaseEntity] = []
    renamed: Dict[str, str] = {}
    seen_entities = set()
    owner_alias = _owner_alias(data.database_entities)
    for entity in data.database_entities:
        original = entity.name
        name = to_pascal(singularize(entity.name)) if entity.name else ""
        if name == "Owner" and owner_alias:
            # A link to 'Owner' records would be called owner_id, the column that records which user owns a row
            name = owner_alias
            renamed["Owner"] = owner_alias
            data.ambiguities.append(f"'{original}' records are generated as {owner_alias} because 'owner' is "
                                    "reserved for record ownership; the screens keep the requested name.")
        if not name or name.lower() in seen_entities or name == "User":
            continue
        seen_entities.add(name.lower())
        renamed[original] = name
        renamed[name] = name
        entity.name = name
        entity.is_system = False
        if entity.access not in ("owner", "admin_managed", "shared"):
            entity.access = "owner"
        entities.append(entity)
    if not entities:
        raise PromptValidationError("Requirement analysis produced no application entities.")
    if len(entities) > MAX_ENTITIES:
        dropped = [e.name for e in entities[MAX_ENTITIES:]]
        entities = entities[:MAX_ENTITIES]
        data.ambiguities.append(f"Only the first {MAX_ENTITIES} entities are generated; not generated: {', '.join(dropped)}.")

    entity_names = {e.name for e in entities} | {"User"}
    field_renames: Dict[str, Dict[str, str]] = {}  # entity -> {old field: new field}

    for entity in entities:
        fields: List[EntityField] = []
        seen = set()
        for f in entity.fields:
            fname = safe_identifier(f.name)
            if owner_alias and entity.name != owner_alias and _links_to_owner(f):
                f.references = owner_alias  # "Pet.owner -> Owner" links to the renamed records, not to a user
                fname = fk_field_name(owner_alias)
                field_renames.setdefault(entity.name, {}).update({"owner_id": fname, "owner": fname})
            if fname in seen or fname in {"id", "created_at", "updated_at", "owner_id", "user_id"}:
                continue
            ftype = _normalize_type(f.type)
            if f.references:
                ref = renamed.get(f.references) or to_pascal(singularize(f.references))
                if ref not in entity_names or ref == entity.name:
                    continue
                f.references = ref
                ftype = "reference"
                fname = fk_field_name(ref)
                if fname in seen:
                    continue
            elif ftype == "reference":
                guess = to_pascal(fname[:-3]) if fname.endswith("_id") else to_pascal(fname)
                if guess in entity_names and guess != entity.name:
                    f.references = guess
                    fname = fk_field_name(guess)
                else:
                    ftype = "integer"
            elif fname.endswith("_id") and to_pascal(fname[:-3]) in entity_names and to_pascal(fname[:-3]) != entity.name:
                ftype = "reference"
                f.references = to_pascal(fname[:-3])
            if ftype == "enum":
                values = [to_snake(v) for v in f.enum_values if str(v).strip()]
                values = list(dict.fromkeys(v for v in values if v))
                if not values:
                    ftype = "string"
                f.enum_values = values
                if values and (f.default is None or to_snake(f.default) not in values):
                    f.default = values[0]
                elif values:
                    f.default = to_snake(f.default)
            else:
                f.enum_values = []
            if ftype == "boolean" and f.default not in ("true", "false"):
                f.default = "false"
            if ftype in ("integer", "float", "decimal"):
                if f.default is not None:
                    try:
                        float(f.default)
                    except (TypeError, ValueError):
                        f.default = None
            elif ftype not in ("enum", "boolean"):
                f.default = None
            f.name = fname
            f.type = ftype
            f.primary_key = False
            f.read_only = False
            f.hidden = False
            f.label = f.label or humanize(fname)
            if ftype in ("text",):
                f.unique = False
            seen.add(fname)
            fields.append(f)
        if not fields:
            fields.append(EntityField(name="name", type="string", nullable=False, searchable=True, label="Name"))
        if not any(f.searchable for f in fields):
            for f in fields:
                if f.type in ("string", "text", "email"):
                    f.searchable = True
                    break

        system_fields = [EntityField(name="id", type="integer", primary_key=True, nullable=False, read_only=True, label="ID")]
        tail = [EntityField(name="created_at", type="datetime", read_only=True, label="Created at")]
        if entity.access == "owner":
            tail.insert(0, EntityField(name="owner_id", type="reference", references="User", read_only=True,
                                       nullable=True, label="Owner"))
        entity.fields = system_fields + fields + tail
        valid_display = {f.name for f in entity.fields if f.type in ("string", "email", "enum", "integer", "text")}
        if entity.display_field not in valid_display:
            entity.display_field = next((f.name for f in fields if f.type in ("string", "email")), "id")

    # Order entities so referenced entities come first (needed by migrations and forms).
    ordered: List[DatabaseEntity] = []
    remaining = list(entities)
    for _ in range(len(entities) + 1):
        for entity in list(remaining):
            deps = {f.references for f in entity.fields if f.references and f.references not in ("User", entity.name)}
            if deps <= {e.name for e in ordered}:
                ordered.append(entity)
                remaining.remove(entity)
    ordered.extend(remaining)
    data.database_entities = [_user_entity(data.user_roles)] + ordered
    names = {e.name for e in ordered}

    # Propagate entity renames into the rest of the specification and drop dangling references.
    for module in data.module_specs:
        module.entities = [renamed.get(e, to_pascal(singularize(e))) for e in module.entities]
        module.entities = [e for e in dict.fromkeys(module.entities) if e in names]
    data.module_specs = [m for m in data.module_specs if m.kind != "entities" or m.entities]
    covered = {e for m in data.module_specs for e in m.entities}
    for e in ordered:
        if e.name not in covered:
            label = humanize(pluralize(to_snake(e.name))).capitalize()
            data.module_specs.append(ModuleSpec(key=to_snake(e.name), name=label, label=label, entities=[e.name]))
    for rule in data.business_rules:
        rule.entity = renamed.get(rule.entity, rule.entity)
        moved = field_renames.get(rule.entity, {})
        rule.fields = [moved.get(name, name) for name in rule.fields]
    for wf in data.workflows:
        wf.entity = renamed.get(wf.entity, wf.entity)
    role_names = {r.name for r in data.user_roles}
    perms: Dict[tuple, RolePermission] = {}
    for p in data.role_permissions:
        role = to_snake(p.role) if to_snake(p.role) != "administrator" else "admin"
        ent = renamed.get(p.entity, to_pascal(singularize(p.entity)))
        if role in role_names and ent in names:
            perms[(role, ent)] = RolePermission(role=role, entity=ent, actions=sorted(set(p.actions) & {"read", "create", "update", "delete"}))
    for role in data.user_roles:
        for e in ordered:
            if (role.name, e.name) in perms:
                continue
            if role.is_admin:
                acts = ["create", "delete", "read", "update"]
            elif e.access == "owner":
                acts = ["create", "delete", "read", "update"]
            elif e.access == "admin_managed":
                acts = ["read"]
            else:
                acts = ["create", "read", "update"]
            perms[(role.name, e.name)] = RolePermission(role=role.name, entity=e.name, actions=acts)
    for (role, ent), p in perms.items():
        if any(r.is_admin and r.name == role for r in data.user_roles):
            p.actions = ["create", "delete", "read", "update"]
        if "read" not in p.actions:
            p.actions = sorted(set(p.actions) | {"read"})
    data.role_permissions = list(perms.values())
    data.seed_records = {renamed.get(k, k): v for k, v in data.seed_records.items() if renamed.get(k, k) in names}

    data.tech_stack = data.tech_stack or TechStack()
    data.requires_auth = True
    _derive_documentation(data)
    return data


def _derive_documentation(data: PMOutput) -> None:
    """Fill features, modules, requirements, dependencies and plan from the specification."""
    app_entities = [e for e in data.database_entities if not e.is_system]
    role_names = ", ".join(r.name for r in data.user_roles)

    features: List[str] = list(dict.fromkeys(f for f in (data.features or []) if f))
    generated = ["User registration and login (JWT authentication)", f"Role-based access control ({role_names})"]
    for m in data.module_specs:
        if m.kind == "entities":
            plural = " and ".join(humanize(pluralize(to_snake(e))).lower() for e in m.entities)
            generated.append(f"{m.name}: create, view, edit and delete {plural}")
        elif m.kind == "reports":
            generated.append("Reports with date filters, status breakdowns and monthly trends")
    for w in data.workflows:
        generated.append(f"{humanize(w.entity).capitalize()} workflow: {' / '.join(t.label for t in w.transitions)}")
    for r in data.business_rules:
        if r.description:
            generated.append(r.description)
    generated.append("Dashboard with live statistics from application data")
    for g in generated:
        if g not in features:
            features.append(g)
    data.features = features

    data.modules = [m.name for m in data.module_specs] or [f"{humanize(e.name)} Management" for e in app_entities]

    if not data.functional_requirements:
        data.functional_requirements = [
            Requirement(id=f"FR-{i:03d}", title=feat, description=feat, priority="must",
                        module=next((m.name for m in data.module_specs if m.name.lower() in feat.lower()), None))
            for i, feat in enumerate(features, start=1)
        ]

    if not data.non_functional_requirements:
        data.non_functional_requirements = [
            Requirement(id="NFR-001", title="Security", description="Passwords hashed with PBKDF2-SHA256; stateless JWT (HS256) sessions; role checks on every protected endpoint."),
            Requirement(id="NFR-002", title="Data integrity", description="Server-side validation of all inputs, foreign key constraints and business rules."),
            Requirement(id="NFR-003", title="Performance", description="Paginated list endpoints and indexed foreign keys."),
            Requirement(id="NFR-004", title="Usability", description="Responsive React interface with search, filters and form validation feedback."),
            Requirement(id="NFR-005", title="Portability", description="PostgreSQL in Docker Compose for deployment; SQLite fallback for local preview."),
            Requirement(id="NFR-006", title="Testability", description="Automated tests generated from the specification and executed for every module."),
        ]

    if not data.dependencies:
        deps = []
        for e in app_entities:
            for f in e.fields:
                if f.type == "reference" and f.references and f.references != "User":
                    deps.append(f"{e.name} depends on {f.references} ({f.name})")
            if e.access == "owner":
                deps.append(f"{e.name} records are owned by a User")
        deps.append("All protected modules depend on Authentication")
        data.dependencies = deps

    if not data.development_plan:
        data.development_plan = [
            DevelopmentTask(step=1, agent="pm", description="Analyse the prompt and produce the application specification"),
            DevelopmentTask(step=2, agent="ui", description="Generate navigation, pages, dashboard and workflows from the specification", depends_on=["pm"]),
            DevelopmentTask(step=3, agent="backend", description="Generate REST APIs, workflow actions and business rules", depends_on=["pm", "ui"]),
            DevelopmentTask(step=4, agent="db", description="Generate models, constraints and PostgreSQL migration", depends_on=["pm", "backend"]),
            DevelopmentTask(step=5, agent="auth", description="Implement registration, login, JWT and role permissions", depends_on=["pm", "backend", "db"]),
            DevelopmentTask(step=6, agent="qa", description="Execute generated tests and check requirement coverage", depends_on=["ui", "backend", "db", "auth"]),
            DevelopmentTask(step=7, agent="deploy", description="Generate Docker/Compose config and verify the running app", depends_on=["qa"]),
        ]
