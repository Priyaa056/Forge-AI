"""Change plan for an iterative refinement.

* :func:`preserve_existing` - safety net: anything in the previous specification that is missing from the
  refined one and was not explicitly removed by the request is put back.
* :func:`diff_specs` - the structural differences (records, fields, modules, roles, permissions,
  workflows, rules, dashboard figures, theme, seed data).
* :func:`build_change_plan` - the differences, which agents must update their files (and why), which
  can reuse the previous version's output, and what was preserved.
"""

from typing import Dict, List, Optional, Sequence, Set, Tuple

from backend.codegen.naming import humanize, to_snake
from backend.schemas.pm_schema import AgentImpact, ChangeItem, ChangePlan, DatabaseEntity, PMOutput

AGENT_ORDER = ["pm", "ui", "backend", "db", "auth", "qa", "deploy"]
AGENT_TITLES = {"pm": "Project Manager", "ui": "UI", "backend": "Backend", "db": "Database", "auth": "Auth",
                "qa": "QA", "deploy": "Deploy"}
CODE_AGENTS = ["ui", "backend", "db", "auth"]
# Which code agents read each part of the specification (see the blueprint attributes each writer uses).
AREA_AGENTS: Dict[str, Set[str]] = {
    "project": {"ui", "backend", "db", "auth"},
    "theme": {"ui"},
    "entity": {"ui", "backend", "db", "auth"},
    "field": {"ui", "backend", "db"},
    "module": {"ui", "backend"},
    "role": {"ui", "backend", "db", "auth"},
    "permission": {"ui", "backend", "auth"},
    "workflow": {"ui", "backend", "db", "auth"},  # new states add action endpoints the auth matrix protects
    "rule": {"ui", "backend", "db"},
    "metric": {"ui", "backend"},
    "seed": {"db"},
}


def _entities(pm: PMOutput) -> Dict[str, DatabaseEntity]:
    return {e.name: e for e in pm.database_entities if not e.is_system}


def _user_fields(e: DatabaseEntity) -> Dict[str, object]:
    return {f.name: f for f in e.fields if not f.read_only and not f.primary_key and not f.hidden}


def _field_kind(f) -> str:
    if f.references:
        return f"reference to {f.references}"
    if f.enum_values:
        return f"{f.type}: {', '.join(f.enum_values)}"
    return f.type


# ---------------------------------------------------------------------------------------------- preservation
def preserve_existing(previous: PMOutput, updated: PMOutput, removed: Set[str]) -> List[str]:
    """Restore items that disappeared without being asked for. Returns what was restored."""
    restored: List[str] = []
    prev_ents, new_ents = _entities(previous), _entities(updated)
    for name, entity in prev_ents.items():
        if name in removed or name in new_ents:
            continue
        refs = {f.references for f in entity.fields if f.references and f.references != "User"}
        if refs - set(new_ents):
            continue  # it depended on a record the request removed
        updated.database_entities.append(entity.model_copy(deep=True))
        updated.role_permissions += [p.model_copy() for p in previous.role_permissions if p.entity == name]
        restored.append(f"{humanize(to_snake(name)).capitalize()} records")
    new_ents = _entities(updated)
    for name, entity in prev_ents.items():
        target = new_ents.get(name)
        if target is None:
            continue
        have = {f.name for f in target.fields}
        for f in entity.fields:
            if f.name in have or f"{name}.{f.name}" in removed:
                continue
            if f.references and f.references not in new_ents and f.references != "User":
                continue
            tail = next((i for i, x in enumerate(target.fields) if x.read_only and x.name in ("owner_id", "created_at")),
                        len(target.fields))
            target.fields.insert(tail, f.model_copy())
            restored.append(f"field {name}.{f.name}")
    keys = {m.key for m in updated.module_specs}
    for m in previous.module_specs:
        ents = [e for e in m.entities if e in new_ents]
        if m.key in keys or f"module:{m.key}" in removed or (m.kind == "entities" and not ents):
            continue
        if m.kind == "entities" and any(e in {x for mm in updated.module_specs for x in mm.entities} for e in ents):
            continue
        updated.module_specs.append(m.model_copy(update={"entities": ents}))
        restored.append(f"module '{m.label}'")
    roles = {r.name for r in updated.user_roles}
    for r in previous.user_roles:
        if r.name not in roles and f"role:{r.name}" not in removed:
            updated.user_roles.append(r.model_copy())
            updated.role_permissions += [p.model_copy() for p in previous.role_permissions
                                         if p.role == r.name and p.entity in new_ents]
            restored.append(f"role '{r.name}'")
    flows = {w.entity for w in updated.workflows}
    for w in previous.workflows:
        if w.entity in new_ents and w.entity not in flows and f"{w.entity}.{w.field}" not in removed:
            updated.workflows.append(w.model_copy(deep=True))
            restored.append(f"{w.entity} workflow")
    rule_keys = {(r.kind, r.entity, tuple(r.fields)) for r in updated.business_rules}
    for r in previous.business_rules:
        e = new_ents.get(r.entity)
        if e is None or (r.kind, r.entity, tuple(r.fields)) in rule_keys:
            continue
        if any(f not in {x.name for x in e.fields} for f in r.fields):
            continue
        updated.business_rules.append(r.model_copy(deep=True))
        restored.append(f"rule '{r.description or r.kind}'")
    metric_keys = {(m.kind, m.entity, m.field, m.value) for m in updated.dashboard_metrics}
    for m in previous.dashboard_metrics:
        if (m.kind, m.entity, m.field, m.value) in metric_keys or f"metric:{m.label}" in removed:
            continue
        if m.entity and m.entity not in new_ents:
            continue
        if m.field and m.entity and m.field not in {x.name for x in new_ents[m.entity].fields}:
            continue
        updated.dashboard_metrics.append(m.model_copy(deep=True))
        restored.append(f"dashboard figure '{m.label}'")
    for key, value in (previous.theme or {}).items():
        if key not in updated.theme:
            updated.theme[key] = value
    return restored


# ---------------------------------------------------------------------------------------------- differences
def _item(action: str, area: str, target: str, detail: str = "") -> ChangeItem:
    return ChangeItem(action=action, area=area, target=target, detail=detail, agents=sorted(AREA_AGENTS[area],
                                                                                            key=AGENT_ORDER.index))


def diff_specs(previous: PMOutput, updated: PMOutput) -> List[ChangeItem]:
    items: List[ChangeItem] = []
    if previous.project_name != updated.project_name:
        items.append(_item("renamed", "project", "Application name", f"{previous.project_name} → {updated.project_name}"))
    for key in sorted(set(previous.theme or {}) | set(updated.theme or {})):
        if (previous.theme or {}).get(key) != (updated.theme or {}).get(key):
            items.append(_item("modified", "theme", humanize(key).capitalize(),
                               f"{(previous.theme or {}).get(key) or 'default'} → {(updated.theme or {}).get(key) or 'default'}"))

    prev_ents, new_ents = _entities(previous), _entities(updated)
    for name in new_ents:
        if name not in prev_ents:
            fields = _user_fields(new_ents[name])
            items.append(_item("added", "entity", name, f"{len(fields)} fields: {', '.join(list(fields)[:8])}"))
    for name in prev_ents:
        if name not in new_ents:
            items.append(_item("removed", "entity", name, "records, page, API and tests removed"))
    for name, before in prev_ents.items():
        after = new_ents.get(name)
        if after is None:
            continue
        if before.access != after.access:
            items.append(_item("modified", "entity", name, f"access {before.access} → {after.access}"))
        bf, af = _user_fields(before), _user_fields(after)
        for fname, f in af.items():
            if fname not in bf:
                items.append(_item("added", "field", f"{name}.{fname}", _field_kind(f)))
        for fname in bf:
            if fname not in af:
                items.append(_item("removed", "field", f"{name}.{fname}"))
        for fname, f in af.items():
            old = bf.get(fname)
            if old is None:
                continue
            changes = []
            if old.type != f.type or (old.references or None) != (f.references or None):
                changes.append(f"{_field_kind(old)} → {_field_kind(f)}")
            elif list(old.enum_values) != list(f.enum_values):
                changes.append(f"values {', '.join(old.enum_values)} → {', '.join(f.enum_values)}")
            if bool(old.nullable) != bool(f.nullable):
                changes.append("optional" if f.nullable else "required")
            if bool(old.unique) != bool(f.unique):
                changes.append("unique" if f.unique else "not unique")
            if changes:
                items.append(_item("modified", "field", f"{name}.{fname}", "; ".join(changes)))

    prev_mods = {m.key: m for m in previous.module_specs}
    new_mods = {m.key: m for m in updated.module_specs}
    for key, m in new_mods.items():
        if key not in prev_mods:
            items.append(_item("added", "module", m.label, ", ".join(m.entities) or m.kind))
    for key, m in prev_mods.items():
        if key not in new_mods:
            items.append(_item("removed", "module", m.label))
            continue
        n = new_mods[key]
        if (m.label, m.name) != (n.label, n.name):
            items.append(_item("renamed", "module", m.label, f"{m.label} → {n.label}"))
        moved = [e for e in set(m.entities) ^ set(n.entities) if e in prev_ents and e in new_ents]
        if moved:
            items.append(_item("modified", "module", n.label, f"records: {', '.join(n.entities)}"))

    prev_roles = {r.name: r for r in previous.user_roles}
    new_roles = {r.name: r for r in updated.user_roles}
    for name in new_roles:
        if name not in prev_roles:
            items.append(_item("added", "role", name, "administrator" if new_roles[name].is_admin else ""))
    for name in prev_roles:
        if name not in new_roles:
            items.append(_item("removed", "role", name))
        elif prev_roles[name].is_admin != new_roles[name].is_admin:
            items.append(_item("modified", "role", name, "administrator" if new_roles[name].is_admin else "not administrator"))
    items += _permission_changes(previous, updated, set(prev_roles) & set(new_roles), set(prev_ents) & set(new_ents))
    for role in set(new_roles) - set(prev_roles):
        grants = {p.entity: p.actions for p in updated.role_permissions if p.role == role}
        detail = "; ".join(f"{e}: {', '.join(a) if a else 'no access'}" for e, a in sorted(grants.items()))
        if detail:
            items.append(_item("added", "permission", role, detail))

    prev_flows = {w.entity: w for w in previous.workflows}
    new_flows = {w.entity: w for w in updated.workflows}
    for entity, w in new_flows.items():
        if entity not in prev_flows:
            items.append(_item("added", "workflow", entity, " → ".join(w.states)))
        elif (prev_flows[entity].states, [t.action for t in prev_flows[entity].transitions]) != \
                (w.states, [t.action for t in w.transitions]):
            items.append(_item("modified", "workflow", entity, " → ".join(w.states)))
    for entity in prev_flows:
        if entity not in new_flows:
            items.append(_item("removed", "workflow", entity))

    rule = lambda r: (r.kind, r.entity, tuple(r.fields))  # noqa: E731
    prev_rules = {rule(r): r for r in previous.business_rules}
    new_rules = {rule(r): r for r in updated.business_rules}
    for key, r in new_rules.items():
        if key not in prev_rules:
            items.append(_item("added", "rule", f"{r.entity}: {r.kind}", r.description))
    for key, r in prev_rules.items():
        if key not in new_rules:
            items.append(_item("removed", "rule", f"{r.entity}: {r.kind}", r.description))

    metric = lambda m: (m.kind, m.entity, m.field, m.value)  # noqa: E731
    prev_metrics = {metric(m): m for m in previous.dashboard_metrics if m.kind != "ask"}
    new_metrics = {metric(m): m for m in updated.dashboard_metrics if m.kind != "ask"}
    for key, m in new_metrics.items():
        if key not in prev_metrics:
            items.append(_item("added", "metric", m.label))
        elif prev_metrics[key].label != m.label:
            items.append(_item("renamed", "metric", m.label, f"{prev_metrics[key].label} → {m.label}"))
    for key, m in prev_metrics.items():
        if key not in new_metrics:
            items.append(_item("removed", "metric", m.label))

    for name in sorted(set(previous.seed_records) | set(updated.seed_records)):
        if name in new_ents and name in prev_ents and previous.seed_records.get(name) != updated.seed_records.get(name):
            items.append(_item("modified", "seed", name, f"{len(updated.seed_records.get(name) or [])} starting records"))
    if previous.demo_data != updated.demo_data:
        items.append(_item("modified", "seed", "Demo data", "on" if updated.demo_data else "off"))
    return items


def _permission_changes(previous: PMOutput, updated: PMOutput, roles: Set[str], entities: Set[str]) -> List[ChangeItem]:
    from backend.codegen.blueprint import build_blueprint

    try:
        before, after = build_blueprint(previous).permissions, build_blueprint(updated).permissions
    except (ValueError, KeyError):
        return []
    items = []
    for role in sorted(roles):
        for entity in sorted(entities):
            a, b = before.get(role, {}).get(entity), after.get(role, {}).get(entity)
            if a is not None and b is not None and sorted(a) != sorted(b):
                items.append(_item("modified", "permission", f"{role} on {entity}",
                                   f"{', '.join(sorted(a)) or 'none'} → {', '.join(sorted(b)) or 'none'}"))
    return items


# ---------------------------------------------------------------------------------------------- plan
def _describe(item: ChangeItem) -> str:
    target = item.target
    if item.area == "entity":
        target = f"{humanize(to_snake(item.target)).capitalize()} records"
    elif item.area == "field":
        target = f"field {item.target}"
    elif item.area in ("module", "role", "metric"):
        noun = "dashboard figure" if item.area == "metric" else item.area
        target = f"{noun} '{item.target}'"
    elif item.area == "workflow":
        target = f"{item.target} workflow"
    elif item.area == "permission":
        target = f"permissions of {item.target}"
    return f"{target} {item.action}" + (f" ({item.detail})" if item.detail and item.area != "entity" else "")


def preserved_counts(previous: PMOutput, updated: PMOutput) -> Dict[str, int]:
    prev_ents, new_ents = _entities(previous), _entities(updated)
    common = set(prev_ents) & set(new_ents)
    fields = sum(1 for e in common for f in _user_fields(prev_ents[e]) if f in _user_fields(new_ents[e]))
    return {
        "records": len(common),
        "fields": fields,
        "modules": len({m.key for m in previous.module_specs} & {m.key for m in updated.module_specs}),
        "roles": len({r.name for r in previous.user_roles} & {r.name for r in updated.user_roles}),
        "workflows": len({w.entity for w in previous.workflows} & {w.entity for w in updated.workflows}),
        "rules": len({(r.kind, r.entity, tuple(r.fields)) for r in previous.business_rules}
                     & {(r.kind, r.entity, tuple(r.fields)) for r in updated.business_rules}),
        "dashboard_figures": len({(m.kind, m.entity, m.field, m.value) for m in previous.dashboard_metrics}
                                 & {(m.kind, m.entity, m.field, m.value) for m in updated.dashboard_metrics}),
    }


def build_change_plan(previous: PMOutput, updated: PMOutput, request: str, applied: Sequence[Tuple[str, List[str]]],
                      unresolved: List[str], notes: List[str], base_run_id: Optional[str] = None,
                      base_version: Optional[int] = None) -> ChangePlan:
    changes = diff_specs(previous, updated)
    reasons: Dict[str, List[str]] = {a: [] for a in CODE_AGENTS}
    for item in changes:
        for agent in item.agents:
            text = _describe(item)
            if text not in reasons[agent]:
                reasons[agent].append(text)
    version = f"v{base_version}" if base_version else "the previous version"
    agents = [AgentImpact(agent="pm", action="plan", reasons=[
        f"Interpreted the change request and produced {len(changes)} change(s) to the specification"])]
    for agent in CODE_AGENTS:
        if reasons[agent]:
            agents.append(AgentImpact(agent=agent, action="update", reasons=reasons[agent][:6] + (
                [f"and {len(reasons[agent]) - 6} more"] if len(reasons[agent]) > 6 else [])))
        else:
            agents.append(AgentImpact(agent=agent, action="reuse", reasons=[
                f"No change affects the {AGENT_TITLES[agent]} agent; its output from {version} is reused"]))
    agents.append(AgentImpact(agent="qa", action="validate", reasons=[
        "Runs the generated tests, requirement coverage and a regression check of every requirement that passed in "
        f"{version}"]))
    agents.append(AgentImpact(agent="deploy", action="package", reasons=[
        "Updates the deployment files and health-checks the refined application"]))
    updating = [AGENT_TITLES[a.agent] for a in agents if a.action == "update"]
    reused = [AGENT_TITLES[a.agent] for a in agents if a.action == "reuse"]
    headline = "; ".join(_describe(c) for c in changes[:3]) + (f"; and {len(changes) - 3} more" if len(changes) > 3 else "")
    summary = (f"{headline[:1].upper()}{headline[1:]}. " if changes else "No changes. ") + \
        (f"Updates: {', '.join(updating)}." if updating else "") + (f" Reuses: {', '.join(reused)}." if reused else "")
    return ChangePlan(
        change_request=request.strip(), base_run_id=base_run_id, base_version=base_version, summary=summary.strip(),
        applied=[op for _, ops in applied for op in ops], changes=changes, agents=agents,
        preserved=preserved_counts(previous, updated), unresolved=list(dict.fromkeys(unresolved)),
        notes=list(dict.fromkeys(notes)),
    )


def render_changelog_entry(plan: ChangePlan, version_label: str) -> str:
    lines = [f"## {version_label}", "", f"_Change request:_ {plan.change_request}", ""]
    lines += [f"- {_describe(c)[:1].upper()}{_describe(c)[1:]}" for c in plan.changes]
    if plan.unresolved:
        lines += ["", "Not applied:"] + [f"- {u}" for u in plan.unresolved]
    lines += ["", "Agents: " + ", ".join(f"{AGENT_TITLES[a.agent]} ({a.action})" for a in plan.agents), ""]
    return "\n".join(lines)
