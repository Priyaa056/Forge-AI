"""Project Manager Agent: converts the user's natural-language idea into structured requirements.

Output: ``requirements.json`` (PMOutput) + ``docs/REQUIREMENTS.md`` in the generated project.
"""

import json
import re
from typing import Any, Dict, List, Optional

from backend.agents.base_agent import BaseAgent
from backend.agents.change_plan import build_change_plan, preserve_existing, render_changelog_entry
from backend.agents.change_request import (
    ChangeOp,
    apply_change_ops,
    apply_change_request,
    find_entities,
    find_module,
)
from backend.agents.pm_analysis import (
    PromptValidationError,
    analyze_prompt,
    finalize_spec,
    normalize_requirements,
    validate_prompt,
)
from backend.artifacts.artifact_context import ArtifactContext
from backend.llm.client import LLMError, extract_json
from backend.schemas.pm_schema import FIELD_TYPES, PMOutput

REFINE_INSTRUCTIONS = """You are the Project Manager agent of FORGE AI. An application already exists (summary below).
The user asks for a change. Translate the request into a list of operations and return ONLY JSON (no markdown):

{"operations": [
  {"op": "add_fields", "entity": "ExistingEntity", "fields": [{"name": "snake_case", "type": "string|text|integer|float|decimal|boolean|date|datetime|time|email|enum|reference", "enum_values": [], "references": "Entity for reference", "required": false}]},
  {"op": "remove_fields", "entity": "ExistingEntity", "fields": ["field_name"]},
  {"op": "remove_entities", "entities": ["ExistingEntity"]},
  {"op": "add_state", "entity": "ExistingEntity", "states": ["snake_case_state"]},
  {"op": "add_role", "role": "snake_case", "permissions": {"ExistingEntity": ["read", "create", "update", "delete"]}, "denied": ["ExistingEntity"]},
  {"op": "remove_role", "role": "existing_role"},
  {"op": "rename_module", "module": "existing module label", "label": "New label"},
  {"op": "rename_project", "name": "New application name"},
  {"op": "theme", "primary_color": "#RRGGBB", "sidebar_color": "#RRGGBB"},
  {"op": "add_metric", "label": "dashboard figure in the user's words"},
  {"op": "remove_metric", "label": "existing dashboard figure"},
  {"op": "add_records", "description": "one sentence describing NEW kinds of records/modules to add, in the user's words"},
  {"op": "unsupported", "text": "part of the request a CRUD web app generator cannot do (payments, uploads, maps, chat ...)"}
],
 "unresolved": ["part of the request that is too vague to apply"]}

Rules: change ONLY what the user asked for; never re-create or rename things that already exist; use the exact
entity names shown below; remove something only if the user explicitly asked to remove it.
"""


class RefinementNoChange(PromptValidationError):
    """A change request that would not change the application."""

AGENT = "pm"

LLM_INSTRUCTIONS = """You are the Project Manager agent of FORGE AI, a multi-agent system that generates full-stack
web applications (React + FastAPI + PostgreSQL). Analyse the user's application idea and return ONLY a JSON object
with this structure (no markdown):

{
  "project_name": "short product name",
  "description": "one paragraph summary of the application",
  "app_type": "snake_case domain, e.g. task_management, ecommerce, healthcare",
  "features": ["user-facing feature", ...],
  "modules": ["module name", ...],
  "user_roles": [{"name": "admin", "description": "...", "is_admin": true}, {"name": "user", "description": "...", "is_admin": false}],
  "database_entities": [
    {"name": "PascalCaseSingular", "description": "...", "access": "owner|admin_managed|shared", "display_field": "field used as label",
     "fields": [{"name": "snake_case", "type": "<TYPE>", "nullable": false, "unique": false, "searchable": true,
                 "enum_values": ["only", "for", "enum"], "references": "OtherEntity (only for type reference)",
                 "min_value": null, "max_value": null, "label": "Human label"}]}
  ],
  "functional_requirements": [{"id": "FR-001", "title": "...", "description": "...", "priority": "must|should|could", "module": "..."}],
  "non_functional_requirements": [{"id": "NFR-001", "title": "...", "description": "...", "priority": "must"}],
  "dependencies": ["Entity A depends on Entity B", ...],
  "assumptions": ["assumption made while interpreting the idea", ...],
  "purpose": "one sentence: what the application is for and who uses it",
  "target_users": ["role names of the people who use it"],
  "module_specs": [{"key": "snake_case", "name": "module name in the user's words", "label": "short nav label",
                    "kind": "entities|reports", "entities": ["EntityName", ...], "description": "..."}],
  "workflows": [{"entity": "EntityName", "field": "status", "states": ["state", ...], "initial": "state",
                 "terminal": ["state"], "transitions": [{"action": "snake_case", "label": "Button label",
                                                         "from_states": ["state"], "to_state": "state"}]}],
  "business_rules": [{"id": "rule_1", "kind": "unique_together|date_order|allocation|computed|low_stock|expiry|overdue",
                      "entity": "EntityName", "fields": ["field", ...], "params": {}, "description": "..."}],
  "dashboard_metrics": [{"id": "m1", "label": "Available beds", "kind": "count|count_where|count_today|upcoming|sum|sum_month|average|alert|breakdown|trend|recent",
                         "entity": "EntityName", "field": "field or null", "value": "status value(s) for count_where"}],
  "role_permissions": [{"role": "role name", "entity": "EntityName", "actions": ["read", "create", "update", "delete"]}],
  "ambiguities": ["missing or unclear requirement and how you resolved it"],
  "unsupported_requests": ["requested capability a CRUD web app generator cannot provide (uploads, payments, maps...)"],
  "theme": {"primary_color": "#hex if the user asked for colours", "sidebar_color": "#hex"},
  "seed_records": {"EntityName": [{"field": "value"}]},
  "demo_data": false
}

Rules:
- <TYPE> is one of: TYPES.
- Model exactly the modules, records, roles, statuses and rules the user asked for, in the user's terminology.
  Never add unrelated generic modules (products, categories, contacts, bookings, employees, ...) that the idea
  does not mention, and never drop a module the user listed. Unfamiliar domains must be modelled as described.
- Do NOT include a User entity, id, created_at, updated_at, owner_id or password fields: authentication, users and
  record ownership are generated by other agents.
- access: "owner" = each user manages their own records (admins see all); "admin_managed" = admins create/edit,
  signed-in users read (catalogues, reference data); "shared" = all signed-in users collaborate on the records.
- Use "reference" fields (with "references") for relationships between entities, e.g. an Admission referencing a Bed.
- Every module listed by the user becomes a module_spec; every status list becomes an enum "status" field and a workflow.
- allocation rules use params {"resource": "Entity", "available": "state", "occupied": "state", "release_states": [..]}.
- Seed records only for values the user listed explicitly (e.g. department names); demo_data true only if asked.
- Up to 25 entities; describe anything ambiguous in "ambiguities" instead of guessing silently.
""".replace("TYPES", ", ".join(FIELD_TYPES))


class PMAgent(BaseAgent[PMOutput]):
    """Requirement analysis agent (LLM-assisted when configured, deterministic otherwise)."""

    stage_name = AGENT

    def __init__(
        self,
        user_prompt: Optional[str] = None,
        output_filepath: str = "outputs/pm_output.json",
        artifact_context: Optional[ArtifactContext] = None,
        project: Optional[Any] = None,
        log_fn=None,
        previous_requirements: Optional[Dict[str, Any]] = None,
        refine: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(output_schema_cls=PMOutput, output_filepath=output_filepath,
                         artifact_context=artifact_context, project=project, log_fn=log_fn)
        self.user_prompt = user_prompt
        self.previous_requirements = previous_requirements
        # Iterative refinement: {"base_run_id": ..., "base_version": ...}; the prompt is a change request
        self.refine = refine if (refine is not None and previous_requirements) else None
        self.plan = None

    def load_inputs(self) -> None:
        prompt = self.user_prompt
        if prompt is None and self.artifact_context is not None:
            prompt = self.artifact_context.user_prompt
        if self.refine is not None:
            self.user_prompt = validate_change_request(prompt)
            self.log(f"Received change request ({len(self.user_prompt)} characters) for version "
                     f"{self.refine.get('base_version') or '?'}")
            return
        self.user_prompt = validate_prompt(prompt)  # raises PromptValidationError for empty/vague prompts
        self.log(f"Received prompt ({len(self.user_prompt)} characters)")

    def _llm_requirements(self, client) -> PMOutput:
        prompt = LLM_INSTRUCTIONS + "\nUSER IDEA:\n" + self.user_prompt
        if self.previous_requirements:
            prompt += ("\n\nThe project already exists with these requirements; apply the user's request as a change "
                       "and return the complete updated requirements:\n" + json.dumps(self.previous_requirements)[:12000])
        last_error: Optional[Exception] = None
        for attempt in (1, 2):
            try:
                raw = extract_json(client.generate_text(prompt, json_mode=True))
                raw.setdefault("description", self.user_prompt)
                pm = PMOutput.model_validate(raw)
                pm.source_prompt = self.user_prompt
                pm.generation_mode = "llm"
                return finalize_spec(normalize_requirements(pm))
            except (LLMError, ValueError) as exc:  # ValueError covers pydantic + PromptValidationError
                last_error = exc
                self.log(f"LLM requirement analysis attempt {attempt} failed: {str(exc)[:200]}", "warning")
        raise LLMError(f"LLM requirement analysis failed: {last_error}")

    def _deterministic_prompt(self) -> str:
        """An iteration is analysed together with the prompt that produced the current version, so the change
        request ("also add a pharmacy", "replace products with patients") is applied to the existing spec."""
        previous = (self.previous_requirements or {}).get("source_prompt") or ""
        if not previous or previous.strip() == self.user_prompt.strip():
            return self.user_prompt
        combined = previous.strip()[: 20000 - len(self.user_prompt) - 40] + "\n\nChange request:\n" + self.user_prompt
        self.log("Iteration: applying the change request to the existing specification")
        return combined

    # ------------------------------------------------------------------ refinement
    def _spec_summary(self, pm: PMOutput) -> str:
        lines = [f"Application: {pm.project_name}"]
        for e in pm.database_entities:
            if e.is_system:
                continue
            fields = ", ".join(f"{f.name}:{f.type}" + (f"->{f.references}" if f.references else "")
                               + (f"[{'/'.join(f.enum_values)}]" if f.enum_values else "")
                               for f in e.fields if not f.read_only and not f.hidden)
            lines.append(f"Entity {e.name} ({e.access}): {fields}")
        lines.append("Modules: " + "; ".join(f"{m.label} ({', '.join(m.entities) or m.kind})" for m in pm.module_specs))
        lines.append("Roles: " + ", ".join(r.name + (" (admin)" if r.is_admin else "") for r in pm.user_roles))
        lines.append("Dashboard: " + "; ".join(m.label for m in pm.dashboard_metrics))
        lines.append(f"Theme: {json.dumps(pm.theme or {})}")
        return "\n".join(lines)

    def _llm_change_ops(self, client, previous: PMOutput):
        prompt = REFINE_INSTRUCTIONS + "\nCURRENT APPLICATION:\n" + self._spec_summary(previous) + \
            "\n\nCHANGE REQUEST:\n" + self.user_prompt
        raw = extract_json(client.generate_text(prompt, json_mode=True))
        if not isinstance(raw, dict) or not isinstance(raw.get("operations"), list):
            raise LLMError("LLM change plan has no 'operations' list")
        ops: List[ChangeOp] = []
        names = {e.name for e in previous.database_entities if not e.is_system}
        for item in raw["operations"]:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("op") or "")
            sentence = self.user_prompt
            if kind in ("add_fields", "remove_fields", "add_state"):
                entity = item.get("entity") if item.get("entity") in names else (find_entities(previous, str(item.get("entity") or "")) or [None])[0]
                if not entity:
                    continue
                if kind == "add_fields":
                    fields = [f for f in item.get("fields") or [] if isinstance(f, dict) and f.get("name")]
                    ops.append(ChangeOp(kind, sentence, {"entity": entity, "fields": fields}))
                elif kind == "remove_fields":
                    ops.append(ChangeOp(kind, sentence, {"entity": entity, "fields": [str(f) for f in item.get("fields") or []]}))
                else:
                    ops.append(ChangeOp(kind, sentence, {"entity": entity, "states": [re.sub(r"\W+", "_", str(s).lower()).strip("_")
                                                                                       for s in item.get("states") or []]}))
            elif kind == "remove_entities":
                targets = [e for e in item.get("entities") or [] if e in names]
                if targets:
                    ops.append(ChangeOp(kind, sentence, {"entities": targets, "module": None}))
            elif kind == "add_role":
                perms = {e: list(a) for e, a in (item.get("permissions") or {}).items() if e in names and isinstance(a, list)}
                ops.append(ChangeOp(kind, sentence, {"role": re.sub(r"\W+", "_", str(item.get("role") or "").lower()).strip("_"),
                                                     "permissions": perms,
                                                     "denied": [e for e in item.get("denied") or [] if e in names]}))
            elif kind == "remove_role":
                ops.append(ChangeOp(kind, sentence, {"role": str(item.get("role") or "")}))
            elif kind == "rename_module":
                module = find_module(previous, str(item.get("module") or ""))
                if module:
                    ops.append(ChangeOp(kind, sentence, {"module": module.key, "label": str(item.get("label") or "")}))
            elif kind == "rename_project":
                ops.append(ChangeOp(kind, sentence, {"name": str(item.get("name") or "")}))
            elif kind == "theme":
                ops.append(ChangeOp(kind, sentence, {k: str(item[k]) for k in ("primary_color", "sidebar_color") if item.get(k)}))
            elif kind in ("add_metric", "remove_metric"):
                ops.append(ChangeOp(kind, sentence, {"label": str(item.get("label") or "")}))
            elif kind == "add_records" and item.get("description"):
                ops.append(ChangeOp(kind, str(item["description"]), {"sentences": [str(item["description"])]}))
            elif kind == "unsupported":
                ops.append(ChangeOp("unsupported", sentence, {"labels": [str(item.get("text") or "unsupported request")]}))
        unresolved = [str(u) for u in raw.get("unresolved") or [] if u]
        if not ops and not unresolved:
            raise LLMError("LLM returned no operations")
        return ops, unresolved

    def _approved_plan(self) -> PMOutput:
        """The specification the user approved in the plan preview, applied exactly (no re-interpretation)."""
        pm = PMOutput.model_validate(self.refine["approved"])
        plan = pm.change_plan
        if plan is None or plan.change_request.strip() != self.user_prompt.strip():
            raise PromptValidationError("The approved plan does not match this change request; preview the change again.")
        if plan.base_run_id and self.refine.get("base_run_id") and plan.base_run_id != self.refine["base_run_id"]:
            raise PromptValidationError("The approved plan was made for a different version; preview the change again.")
        self.generation_mode = pm.generation_mode or "deterministic"
        self.plan = plan
        self.log(f"Applying the change plan approved in the preview: {plan.summary}")
        for line in plan.applied:
            self.log(f"Change: {line}")
        return pm

    def _refine(self) -> PMOutput:
        if self.refine.get("approved"):
            return self._approved_plan()
        previous = PMOutput.model_validate(self.previous_requirements)
        previous.change_plan = None
        result = None
        client = self.get_llm()
        if client is not None:
            try:
                ops, unresolved = self._llm_change_ops(client, previous)
                result = apply_change_ops(previous, ops, self.user_prompt, unresolved)
                self.generation_mode = "llm"
            except (LLMError, ValueError, KeyError, TypeError) as exc:
                self.log(f"LLM change analysis failed ({str(exc)[:150]}); using rule-based analysis", "warning")
        if result is None:
            result = apply_change_request(previous, self.user_prompt)
            self.generation_mode = "deterministic" if client is None else "deterministic_fallback"
        restored = preserve_existing(previous, result.pm, result.removed)
        notes = list(result.notes) + [f"Kept {r} (the request did not ask to remove it)" for r in restored]
        plan = build_change_plan(previous, result.pm, self.user_prompt, result.applied, result.unresolved, notes,
                                 base_run_id=self.refine.get("base_run_id"), base_version=self.refine.get("base_version"))
        for line in plan.applied:
            self.log(f"Change: {line}")
        for line in plan.unresolved:
            self.log(f"Not applied: {line}", "warning")
        if not plan.changes:
            reason = " ".join(plan.unresolved + plan.notes) or "The request did not describe a change FORGE AI can apply."
            raise RefinementNoChange(f"No change to apply: {reason} The current version stays live.")
        pm = result.pm
        pm.change_plan = plan
        pm.generation_mode = self.generation_mode
        self.plan = plan
        self.log(f"Change plan: {plan.summary}")
        kept = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in plan.preserved.items() if v)
        self.log(f"Preserved from version {self.refine.get('base_version') or '?'}: {kept}")
        return pm

    def generate(self) -> Dict[str, Any]:
        if self.refine is not None:
            return self._refine().model_dump()
        client = self.get_llm()
        pm: Optional[PMOutput] = None
        if client is not None:
            self.log(f"Analysing requirements with {getattr(client, 'name', 'LLM')}")
            try:
                pm = self._llm_requirements(client)
                self.generation_mode = "llm"
            except LLMError as exc:
                self.log(f"{exc}. Falling back to deterministic requirement analysis.", "warning")
        if pm is None:
            pm = analyze_prompt(self._deterministic_prompt())
            self.generation_mode = "deterministic" if client is None else "deterministic_fallback"
            pm.generation_mode = self.generation_mode
        entities = [e.name for e in pm.database_entities if not e.is_system]
        self.log(f"Project '{pm.project_name}' ({pm.app_type}); entities: {', '.join(entities)}")
        self.log(f"Roles: {', '.join(r.name for r in pm.user_roles)}; {len(pm.functional_requirements)} functional requirements")
        self.log(f"Modules: {', '.join(m.label for m in pm.module_specs)}; {len(pm.workflows)} workflows, "
                 f"{len(pm.business_rules)} business rules, {len(pm.dashboard_metrics)} dashboard metrics")
        if pm.unsupported_requests:
            self.log(f"Not supported by the generator: {'; '.join(pm.unsupported_requests)}", "warning")
        return pm.model_dump()

    def emit_code(self, output: PMOutput) -> List[str]:
        self.project.write("docs/REQUIREMENTS.md", render_requirements_doc(output), AGENT)
        if output.change_plan is not None and self.refine is not None:
            base = self.refine.get("base_version")
            label = f"Refinement of v{base}" if base else "Refinement"
            existing = self.project.read("docs/CHANGELOG.md") if self.project.exists("docs/CHANGELOG.md") else ""
            body = existing.split("\n", 2)[2] if existing.startswith("# Changelog") else existing
            self.project.write("docs/CHANGELOG.md", "# Changelog\n\n" + render_changelog_entry(output.change_plan, label)
                               + ("\n" + body.lstrip("\n") if body.strip() else ""), AGENT)
        return self.project.files_by_agent(AGENT)


def render_requirements_doc(pm: PMOutput) -> str:
    lines = [f"# {pm.project_name} - Requirements", "", f"_Source prompt:_ {pm.source_prompt}", "",
             f"Generation mode: **{pm.generation_mode}**", "", "## Summary", pm.description, "", "## Roles"]
    lines += [f"- **{r.name}**{' (admin)' if r.is_admin else ''}: {r.description}" for r in pm.user_roles]
    lines += ["", "## Modules"] + [f"- {m}" for m in pm.modules]
    lines += ["", "## Entities"]
    for e in pm.database_entities:
        lines.append(f"### {e.name} ({e.access})")
        lines += [f"- `{f.name}`: {f.type}" + (f" -> {f.references}" if f.references else "")
                  + (f" [{', '.join(f.enum_values)}]" if f.enum_values else "")
                  + (" required" if not f.nullable else "") for f in e.fields if not f.hidden]
    lines += ["", "## Functional requirements"]
    lines += [f"- **{r.id}** ({r.priority}) {r.title}" for r in pm.functional_requirements]
    lines += ["", "## Non-functional requirements"]
    lines += [f"- **{r.id}** {r.title}: {r.description}" for r in pm.non_functional_requirements]
    lines += ["", "## Dependencies"] + [f"- {d}" for d in pm.dependencies]
    if pm.assumptions:
        lines += ["", "## Assumptions"] + [f"- {a}" for a in pm.assumptions]
    lines += ["", "## Development plan"]
    lines += [f"{t.step}. **{t.agent}**: {t.description}" for t in pm.development_plan]
    return "\n".join(lines) + "\n"


def validate_change_request(text: Optional[str]) -> str:
    value = (text or "").strip()
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", value)
    if len(value) < 8 or len(words) < 2:
        raise PromptValidationError("Describe the change you want, e.g. 'Add a phone number field to members' or "
                                    "'Remove the fines module'.")
    if len(value) > 5000:
        raise PromptValidationError("The change request is longer than 5,000 characters; describe one set of changes at a time.")
    return value


def generate_pm_output(user_prompt: str) -> str:
    """Backwards-compatible helper (original PM entry point): returns requirements JSON text."""
    agent = PMAgent(user_prompt=user_prompt)
    agent.load_inputs()
    data = agent.generate()
    PMOutput.model_validate(data)
    return json.dumps(data)


__all__ = ["PMAgent", "generate_pm_output", "PromptValidationError"]
