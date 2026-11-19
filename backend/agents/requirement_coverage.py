"""Requirement-based QA: compare the prompt's specification with what was actually generated.

Every item of the specification (modules, entities, fields, roles, role permissions, workflow
steps, business rules, dashboard metrics, listed records) is looked up in the generated files and
the registered API routes. Missing items become targeted correction tasks for the agent that owns
them; capabilities the generator cannot build are reported as unsupported instead of being hidden.

The evidence is read from the generated project, not from the blueprint, so a project cannot pass
merely because the specification is internally consistent or because the frontend builds.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.codegen.blueprint import build_blueprint
from backend.schemas.pm_schema import PMOutput

AGENT_STAGE = {"ui": "UIAgent", "backend": "BackendAgent", "db": "DBAgent", "auth": "AuthAgent", "qa": "QAAgent"}
FIXED_NAV = {"Dashboard", "Admin", "Reports"}


def _read(root: Path, rel: str) -> str:
    path = root / rel
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError:
        return ""


def _js_exports(source: str) -> Dict[str, Any]:
    """Parse ``export const NAME = <json>;`` declarations written by the UI agent."""
    out: Dict[str, Any] = {}
    for m in re.finditer(r"export const (\w+) = (.*?);\s*(?=\nexport const |\Z)", source, re.S):
        try:
            out[m.group(1)] = json.loads(m.group(2))
        except ValueError:
            continue
    return out


def _norm(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{id}", path.rstrip("/")) or "/"


def check_requirement_coverage(pm: PMOutput, root: Path, routes: Optional[Sequence[Tuple[str, str]]] = None) -> Dict[str, Any]:
    root = Path(root)
    bp = build_blueprint(pm)
    items: List[Dict[str, Any]] = []

    def item(kind: str, requirement: str, ok: bool, evidence: str, agent: str, issue: str = "") -> None:
        items.append({"kind": kind, "requirement": requirement, "status": "covered" if ok else "missing",
                      "evidence": evidence if ok else "", "agent": AGENT_STAGE[agent], "issue": "" if ok else issue})

    app_cfg = _js_exports(_read(root, "frontend/src/config/app.js"))
    ent_cfg = _js_exports(_read(root, "frontend/src/config/entities.js")).get("ENTITIES", {})
    app_jsx = _read(root, "frontend/src/App.jsx")
    models = _read(root, "backend/app/models.py")
    security = _read(root, "backend/app/security.py")
    dashboard = _read(root, "backend/app/routers/dashboard.py")
    seed = _read(root, "backend/app/seed_data.py")
    rule_tests = _read(root, "backend/tests/test_business_rules.py")
    workflow_tests = _read(root, "backend/tests/test_workflows.py")
    nav = app_cfg.get("NAV_ITEMS", [])
    nav_by_label = {n.get("label"): n for n in nav}
    route_paths = set(re.findall(r'<Route\s+path="([^"]+)"', app_jsx))
    registered = {(m.upper(), _norm(p)) for m, p in (routes or [])}
    model_classes = set(re.findall(r"^class (\w+)\(Base\):", models, re.M))
    role_perms: Dict[str, set] = {}
    for m in re.finditer(r'^\s+"([\w-]+)": (\{[^}\n]*\}|set\(\)),', security, re.M):
        role_perms[m.group(1)] = set(re.findall(r"'([^']+)'", m.group(2)))

    # ---- modules / navigation / pages
    for module in bp.modules:
        if module.kind == "reports":
            ok_nav = "Reports" in nav_by_label and "reports" in route_paths
            ok_api = not routes or ("GET", "/api/reports") in registered
            item("module", "Reports module", ok_nav and ok_api, "nav 'Reports', route /reports, GET /api/reports",
                 "ui" if not ok_nav else "backend", "Reports page or /api/reports endpoint missing")
            continue
        entry = nav_by_label.get(module.label)
        ok = bool(entry) and set(entry.get("entities", [])) == set(module.entities) and module.path.lstrip("/") in route_paths
        item("module", f"Module '{module.name}'", ok, f"nav '{module.label}' -> {module.path} ({', '.join(module.entities)})",
             "ui", f"Navigation item/page for '{module.label}' missing or showing the wrong records")
    spec_labels = {m.label for m in bp.modules}
    for label in nav_by_label:
        if label not in spec_labels and label not in FIXED_NAV:
            item("module", f"No unrequested module ('{label}')", False, "", "ui",
                 f"Navigation shows '{label}', which the prompt did not ask for")

    # ---- entities, fields, CRUD endpoints
    for e in bp.entities:
        cfg = ent_cfg.get(e.name)
        item("entity", f"Entity {e.name} model", e.name in model_classes, f"class {e.name}(Base) in models.py", "db",
             f"SQLAlchemy model {e.name} missing")
        if routes:
            needed = {("GET", e.api_path), ("POST", e.api_path), ("GET", f"{e.api_path}/{{id}}"),
                      ("PUT", f"{e.api_path}/{{id}}"), ("DELETE", f"{e.api_path}/{{id}}")}
            missing = sorted(f"{m} {p}" for m, p in needed - registered)
            item("entity", f"Entity {e.name} API", not missing, f"CRUD routes under {e.api_path}", "backend",
                 "Missing routes: " + ", ".join(missing))
        item("entity", f"Entity {e.name} UI", bool(cfg), f"ENTITIES.{e.name} in config/entities.js", "ui",
             f"No UI configuration for {e.name}")
        ui_fields = {f.get("name") for f in (cfg or {}).get("fields", [])}
        model_block = models.split(f"class {e.name}(Base):", 1)[1].split("\nclass ", 1)[0] if e.name in model_classes else ""
        for f in e.fields:
            if f.hidden or f.primary_key or f.name in ("created_at", "owner_id"):
                continue
            in_model = re.search(rf"^    {re.escape(f.name)}: Mapped", model_block, re.M) is not None
            ok = in_model and f.name in ui_fields
            item("field", f"{e.name}.{f.name}", ok, "model column + form/table field", "db" if not in_model else "ui",
                 f"Field {f.name} missing from the {'model' if not in_model else 'UI'}")

    # ---- roles and permissions (backend matrix and UI matrix must match the specification)
    ui_perms = app_cfg.get("PERMISSIONS", {})
    for role in bp.roles:
        ok = role in role_perms and role in ui_perms
        item("role", f"Role '{role}'", ok, "ROLE_PERMISSIONS (security.py) and PERMISSIONS (app.js)", "auth",
             f"Role {role} missing from the RBAC matrix")
        if not ok or role in bp.admin_roles:
            continue
        for e in bp.entities:
            want = set(bp.permissions.get(role, {}).get(e.name, []))
            granted = {a for a in ("read", "create", "update", "delete") if e.permission(a) in role_perms.get(role, set())}
            ui_granted = set(ui_perms.get(role, {}).get(e.name, []))
            ok = granted == want and ui_granted == want
            item("permission", f"{role} on {e.name}: {', '.join(sorted(want)) or 'none'}", ok,
                 "backend + UI permission matrices", "auth" if granted != want else "ui",
                 f"backend grants {sorted(granted)}, UI grants {sorted(ui_granted)}, spec requires {sorted(want)}")

    # ---- workflows
    for entity, wf in bp.workflows.items():
        e = bp.entity(entity)
        router = _read(root, f"backend/app/routers/{e.plural_snake}.py")
        ui_actions = {t.get("action") for t in ((ent_cfg.get(entity) or {}).get("workflow") or {}).get("transitions", [])}
        route_ok = not routes or ("POST", f"{e.api_path}/{{id}}/actions/{{id}}") in registered
        for t in wf.get("transitions", []):
            in_router = f'"{t["action"]}":' in router
            ok = route_ok and in_router and t["action"] in ui_actions
            item("workflow", f"{entity}: {t['label']} -> {t['to_state']}", ok,
                 f"POST {e.api_path}/{{id}}/actions/{t['action']} + UI button",
                 "backend" if not (route_ok and in_router) else "ui", f"Workflow step {t['action']} not implemented")
        tested = f"def test_{e.snake}_" in workflow_tests
        item("test", f"{entity} workflow tested", tested, "tests/test_workflows.py", "qa", "No generated workflow test")

    # ---- business rules
    for r in bp.rules:
        e = bp.entity(r["entity"])
        router = _read(root, f"backend/app/routers/{e.plural_snake}.py")
        fields = r.get("fields") or []
        block = {"date_order": "DATE_ORDER", "computed": "COMPUTED", "unique_together": "UNIQUE_TOGETHER",
                 "allocation": "ALLOCATIONS"}.get(r["kind"])
        if block:
            found = re.search(rf"^{block} = (.*?)(?=^[A-Z_]+ = |\Z)", router, re.S | re.M)
            section = found.group(1) if found else ""
            ok = bool(section) and all(f'"{f}"' in section for f in fields)
            item("rule", r.get("description") or f"{r['kind']} on {e.name}", ok, f"{block} in routers/{e.plural_snake}.py",
                 "backend", f"Rule {r['kind']} ({', '.join(fields)}) not enforced by the {e.name} API")
            item("test", f"Rule {r['kind']} on {e.name} tested", f"def test_{e.snake}_" in rule_tests,
                 "tests/test_business_rules.py", "qa", "No generated test for this rule")
        else:  # low_stock / expiry / overdue are surfaced as dashboard alerts
            ok = f'"rule": "{r["kind"]}"' in dashboard
            item("rule", r.get("description") or f"{r['kind']} on {e.name}", ok, "dashboard alert metric", "backend",
                 f"{r['kind']} alert not on the dashboard")

    # ---- dashboard metrics
    for m in bp.metrics:
        ok = f'"id": "{m["id"]}"' in dashboard and json.dumps(m["label"])[1:-1] in dashboard
        item("metric", f"Dashboard: {m['label']}", ok, "METRICS in routers/dashboard.py", "backend",
             f"Dashboard metric '{m['label']}' not implemented")
    if routes:
        item("metric", "Dashboard metrics endpoint", ("GET", "/api/dashboard/metrics") in registered,
             "GET /api/dashboard/metrics", "backend", "Metrics endpoint missing")
    prompt_head = (pm.source_prompt or "").strip()[:80]
    shows_prompt = len(pm.source_prompt or "") > 120 and prompt_head and prompt_head in _read(root, "frontend/src/config/app.js")
    item("page", "Dashboard does not display the generation prompt", not shows_prompt, "APP_PURPOSE is a one-sentence purpose",
         "ui", "The raw prompt is shown as dashboard content")

    # ---- records listed in the prompt
    for name, rows in bp.seed_records.items():
        for row in rows:
            value = next(iter(row.values()), None)
            ok = value is not None and json.dumps(value) in seed
            item("seed", f"{name} record '{value}'", ok, "SEED_RECORDS in seed_data.py", "db",
                 f"Listed record '{value}' is not seeded")

    unsupported = list(pm.unsupported_requests)
    for label in unsupported:
        items.append({"kind": "feature", "requirement": label, "status": "unsupported", "evidence": "", "agent": "",
                      "issue": "FORGE AI cannot generate this capability; it was not faked"})

    missing = [i for i in items if i["status"] == "missing"]
    tasks: Dict[str, Dict[str, Any]] = {}
    for i in missing:
        task = tasks.setdefault(i["agent"], {"agent": i["agent"], "requirements": [], "issues": []})
        task["requirements"].append(i["requirement"])
        task["issues"].append(i["issue"])
    covered = sum(1 for i in items if i["status"] == "covered")
    return {
        "items": items,
        "covered": covered,
        "missing": len(missing),
        "unsupported": unsupported,
        "correction_tasks": list(tasks.values()),
        "summary": f"{covered}/{covered + len(missing)} specification items implemented"
                   + (f"; {len(unsupported)} unsupported request(s) reported" if unsupported else ""),
    }
