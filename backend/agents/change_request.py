"""Iterative refinement: apply a change request to the requirements of an existing application.

The previous requirements are the starting point. The request is split into sentences and each sentence
is turned into operations (deterministically here, or by the LLM in ``pm_agent``) that are applied to a
copy of the specification:

* ``add_fields``     "Add a phone number and membership type (student, staff, public) to members"
* ``remove_fields``  "Remove the notes field from loans"
* ``remove_entity``  "Remove the fines module"
* ``add_state``      "Add a 'lost' status to loans"
* ``add_role``       "Add a librarian role who can manage books and loans but not members"
* ``remove_role``    "Remove the librarian role"
* ``rename_module``  "Rename the Books module to Catalogue"
* ``rename_project`` "Rename the app to City Library"
* ``theme``          "Change the primary colour to green"
* ``add_metric``     "Add a dashboard card showing overdue loans"
* ``add_records``    "Add a book reservations module where members reserve books" (prompt analysis)

Only what a request touches changes; everything else is copied unchanged, so existing features are kept
by construction. Sentences that cannot be applied are reported as unresolved, never silently ignored.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.agents import attribute_lexicon as lex
from backend.agents.spec_extraction import (
    UNSUPPORTED,
    _clean_phrase,
    _sentences,
    _shade,
    _strip_markup,
    infer_field,
)
from backend.codegen.naming import fk_field_name, humanize, pluralize, safe_identifier, singularize, to_pascal, to_snake
from backend.schemas.pm_schema import (
    DashboardMetric,
    DatabaseEntity,
    EntityField,
    ModuleSpec,
    PMOutput,
    Requirement,
    RolePermission,
    TraceItem,
    UserRole,
)

CRUD = ["create", "delete", "read", "update"]
VERB_ACTIONS = {
    "manage": CRUD, "handle": CRUD, "administer": CRUD, "maintain": CRUD, "control": CRUD, "own": CRUD,
    "view": ["read"], "see": ["read"], "read": ["read"], "browse": ["read"], "access": ["read"], "check": ["read"],
    "monitor": ["read"], "list": ["read"],
    "create": ["create", "read"], "add": ["create", "read"], "register": ["create", "read"], "record": ["create", "read"],
    "log": ["create", "read"], "issue": ["create", "read", "update"], "book": ["create", "read"],
    "edit": ["read", "update"], "update": ["read", "update"], "modify": ["read", "update"], "change": ["read", "update"],
    "approve": ["read", "update"], "process": ["read", "update"],
    "delete": ["delete", "read"], "remove": ["delete", "read"],
}
CONTAINER_WORDS = {"module", "modules", "page", "pages", "section", "sections", "feature", "features", "screen", "screens",
                   "tab", "tabs", "record", "records", "management", "functionality", "menu", "list", "table", "tables",
                   "data", "entity", "entities", "form", "forms", "item", "items", "details", "information", "area"}
FIELD_WORDS = {"field", "fields", "column", "columns", "attribute", "attributes", "property", "properties", "input"}
REMOVE_VERBS = r"(?:remove|delete|drop|get rid of|take out|eliminate|discard|hide)"
ADD_VERBS = r"(?:add|include|introduce|create|build|support|enable|allow|implement|provide|need|want|track|store|record|capture)"
VAGUE = re.compile(r"\b(nicer|better|prettier|modern(?:ise|ize)?|improve|polish|clean ?up|fix (?:the )?bugs?|faster|"
                   r"more (?:professional|beautiful|user[- ]friendly)|look good|redesign)\b", re.I)


@dataclass
class ChangeOp:
    """One structured edit to the specification."""
    kind: str
    sentence: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChangeResult:
    pm: PMOutput
    applied: List[Tuple[str, List[str]]]   # (sentence, human-readable operations)
    unresolved: List[str]                  # sentences / items that could not be applied, with the reason
    removed: Set[str]                      # explicit removal targets ("Fine", "Loan.notes", "role:librarian", "module:fines")
    notes: List[str]


class ChangeRequestError(ValueError):
    """The request could not be turned into any change."""


# ---------------------------------------------------------------------------------------------- text helpers
def split_request(request: str) -> List[str]:
    """Sentences and verb-led clauses ("Add X to members and remove the fines module")."""
    text = _strip_markup(request or "")
    out: List[str] = []
    for sentence in _sentences(text):
        sentence = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", sentence)
        for clause in re.split(r"\s*;\s*|,?\s+(?:and|then|also)\s+(?:then\s+|also\s+)?(?=(?:please\s+)?(?:add|remove|delete|drop|"
                               r"rename|change|make|include|create|introduce|show|display|hide)\b)",
                               sentence, flags=re.I):
            clause = clause.strip(" .!")
            if clause:
                out.append(clause)
    return out


def _split_items(text: str) -> List[str]:
    """'a phone number, membership type (student, staff) and notes' -> items, keeping '(...)' with its item."""
    items, depth, current = [], 0, ""
    tokens = re.split(r"(\(|\)|,|;|\band\b|&)", text)
    for tok in tokens:
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth = max(0, depth - 1)
        if depth == 0 and tok in (",", ";", "and", "&"):
            items.append(current)
            current = ""
        else:
            current += tok
    items.append(current)
    return [i.strip(" .:-") for i in items if i and i.strip(" .:-")]


def _values_in(item: str) -> Tuple[str, List[str]]:
    """'membership type (student, staff, public)' -> ('membership type', ['student', 'staff', 'public'])."""
    m = re.search(r"\(([^)]*)\)", item)
    if not m:
        m2 = re.search(r"\s+(?:with values|such as|like|either)\s+(.+)$", item, re.I)
        if not m2:
            return item, []
        values = [v.strip(" '\"") for v in re.split(r"\s*(?:,|/|\bor\b|\band\b)\s*", m2.group(1)) if v.strip(" '\"")]
        return item[:m2.start()].strip(), values
    values = [v.strip(" '\"") for v in re.split(r"\s*(?:,|/|\bor\b|\band\b)\s*", m.group(1)) if v.strip(" '\"")]
    return (item[:m.start()] + item[m.end():]).strip(), values


def _content_words(phrase: str) -> List[str]:
    words = _clean_phrase(phrase)
    while words and words[-1] in CONTAINER_WORDS | FIELD_WORDS:
        words = words[:-1]
    return words


# ---------------------------------------------------------------------------------------------- lookups
def _app_entities(pm: PMOutput) -> List[DatabaseEntity]:
    return [e for e in pm.database_entities if not e.is_system]


def _entity_names(e: DatabaseEntity) -> Set[str]:
    snake = to_snake(e.name)
    return {snake, snake.replace("_", " "), humanize(snake).lower(), humanize(pluralize(snake)).lower(),
            pluralize(snake).replace("_", " ")}


def find_entities(pm: PMOutput, phrase: str, exact: bool = False) -> List[str]:
    """Entities a phrase refers to: a record name ('loans', 'book reservations') or a module label ('Fines').

    ``exact`` (used for removals) disables the loose last-word match, so 'notes field from members' or
    'overdue loans' never resolve to a whole record by accident.
    """
    words = _content_words(phrase)
    if not words:
        return []
    text = " ".join(words)
    single = " ".join(words[:-1] + [singularize(words[-1])])
    for e in _app_entities(pm):
        if text in _entity_names(e) or single in _entity_names(e):
            return [e.name]
    for m in pm.module_specs:
        names = {m.label.lower(), m.name.lower(), m.key.replace("_", " ")}
        names |= {re.sub(r"\s+(management|module|tracking)$", "", n) for n in names}
        if text in names or single in names or " ".join(singularize(w) for w in words) in {singularize(n) for n in names}:
            return [e for e in m.entities if any(x.name == e for x in _app_entities(pm))]
    if exact or len(words) > 2:
        return []
    heads = [e.name for e in _app_entities(pm) if to_snake(e.name).split("_")[-1] == singularize(words[-1])]
    return heads if len(heads) == 1 else []


def find_module(pm: PMOutput, phrase: str) -> Optional[ModuleSpec]:
    words = _content_words(phrase)
    if not words:
        return None
    text = " ".join(words)
    for m in pm.module_specs:
        if text in {m.label.lower(), m.name.lower(), m.key.replace("_", " ")} or \
                singularize(text) in {singularize(m.label.lower()), singularize(m.name.lower())}:
            return m
    ents = find_entities(pm, phrase)
    return next((m for m in pm.module_specs if ents and ents[0] in m.entities), None)


def _entity(pm: PMOutput, name: str) -> Optional[DatabaseEntity]:
    return next((e for e in pm.database_entities if e.name == name), None)


def find_field(entity: DatabaseEntity, phrase: str) -> Optional[EntityField]:
    words = _content_words(phrase)
    if not words:
        return None
    candidates = {safe_identifier("_".join(words)), safe_identifier("_".join(words[:-1] + [singularize(words[-1])]))}
    candidates |= {c + "_id" for c in list(candidates)}
    inferred = infer_field(words, to_snake(entity.name))
    if inferred:
        candidates.add(inferred.name)
    label = " ".join(words)
    for f in entity.fields:
        if f.read_only or f.hidden or f.primary_key:
            continue
        if f.name in candidates or (f.label or "").lower() == label:
            return f
    return None


# ---------------------------------------------------------------------------------------------- parsing
def parse_change_request(pm: PMOutput, request: str) -> Tuple[List[ChangeOp], List[str]]:
    """Deterministic interpretation: (operations, unresolved sentences)."""
    ops: List[ChangeOp] = []
    unresolved: List[str] = []
    generic: List[str] = []
    for sentence in split_request(request):
        low = sentence.lower()
        unsupported = [label for pattern, label in UNSUPPORTED if re.search(pattern, low)]
        if unsupported and not re.match(rf"^\s*{REMOVE_VERBS}\b", low) and not set(re.findall(r"[a-z]+", low)) & FIELD_WORDS:
            ops.append(ChangeOp("unsupported", sentence, {"labels": unsupported}))
            continue
        found = _parse_sentence(pm, sentence, low)
        if found is None:
            if VAGUE.search(low) and not re.search(r"\b(module|records?|fields?|role|status|colou?r)\b", low):
                unresolved.append(f"“{sentence}” is too general to apply; describe the concrete change "
                                  "(e.g. a module, record, field, role, status or colour).")
            else:
                generic.append(sentence)
        else:
            ops.extend(found)
    if generic:
        ops.append(ChangeOp("add_records", " ".join(generic), {"sentences": generic}))
    return ops, unresolved


def _parse_sentence(pm: PMOutput, sentence: str, low: str) -> Optional[List[ChangeOp]]:
    s = re.sub(r"^(?:please\s+|can you\s+|could you\s+|i want to\s+|i'd like to\s+|we need to\s+|also\s+)+", "", low).strip()

    # ---- theme / colours
    colors = "|".join(lex.COLOR_WORDS)
    if re.search(rf"\b({colors})\b", s) and re.search(r"\b(theme|colou?rs?|accent|primary|palette|sidebar|side bar|"
                                                       r"navigation|branding|buttons?|header)\b", s):
        theme: Dict[str, str] = {}
        side = re.search(rf"\b(dark|deep|light)?\s*({colors})(?:[- ]and[- ]\w+)?\s+(?:side\s?bar|navigation|menu)\b", s) or \
            re.search(rf"\b(?:side\s?bar|navigation|menu)\b.*?\b(?:to|in|as)\s+(dark|deep|light)?\s*({colors})\b", s)
        if side:
            theme["sidebar_color"] = _shade(lex.COLOR_WORDS[side.group(2)], side.group(1))
        if not side or re.search(r"\b(primary|accent|buttons?|theme|main)\b", s):
            rest = s if not side else s[:side.start()] + s[side.end():]
            chosen = re.search(rf"\b(dark|deep|light)?\s*({colors})\b", rest)
            if chosen:
                theme["primary_color"] = _shade(lex.COLOR_WORDS[chosen.group(2)], chosen.group(1))
        if theme:
            return [ChangeOp("theme", sentence, theme)]

    # ---- rename the application
    m = re.match(r"^(?:rename|call)\s+(?:the\s+)?(?:app|application|project|system|site|product)\s+(?:to\s+|as\s+)?"
                 r"[\"']?(?P<new>[^\"']+?)[\"']?$", s)
    if m:
        return [ChangeOp("rename_project", sentence, {"name": _title(sentence, m.group("new"))})]

    # ---- rename a module
    m = re.match(r"^(?:rename|relabel)\s+(?:the\s+)?[\"']?(?P<old>.+?)[\"']?\s+(?:(?:module|page|section|tab|menu item|menu)\s+)?"
                 r"(?:to|as|into)\s+[\"']?(?P<new>[^\"']+?)[\"']?$", s) or \
        re.match(r"^call\s+the\s+(?P<old>.+?)\s+(?:module|page|section|tab)\s+[\"']?(?P<new>[^\"']+?)[\"']?$", s)
    if m:
        module = find_module(pm, m.group("old"))
        if module:
            return [ChangeOp("rename_module", sentence, {"module": module.key, "label": _title(sentence, m.group("new"))})]

    # ---- roles
    m = re.match(rf"^{REMOVE_VERBS}\s+(?:the\s+)?(?P<role>[a-z][a-z ]*?)\s+role\b", s)
    if m:
        role = to_snake(m.group("role"))
        if any(r.name == role for r in pm.user_roles):
            return [ChangeOp("remove_role", sentence, {"role": role})]
    m = re.match(r"^(?:add|create|introduce|include|we need|i need|there should be)\s+(?:a\s+|an\s+|new\s+|another\s+)*"
                 r"(?:new\s+)?(?P<role>[a-z][a-z ]{1,40}?)\s+(?:user\s+)?role\b(?P<rest>.*)$", s)
    if m:
        return [ChangeOp("add_role", sentence, _role_params(pm, m.group("role"), m.group("rest")))]

    # ---- dashboard figures
    m = re.match(r"^(?:add|show|display|include|put)\s+(?:a\s+|an\s+|new\s+|the\s+)*(?:dashboard\s+)?"
                 r"(?:card|metric|widget|stat|statistic|kpi|figure|counter|chart|graph|tile|number)s?\s+"
                 r"(?:showing|for|with|that shows|displaying|of|to show|about)\s+(?P<what>.+)$", s) or \
        re.match(r"^(?:show|display|add|include)\s+(?:the\s+)?(?P<what>.+?)\s+(?:on|to|in)\s+the\s+dashboard$", s)
    if m:
        return [ChangeOp("add_metric", sentence, {"label": m.group("what").strip()})]
    m = re.match(rf"^{REMOVE_VERBS}\s+(?:the\s+)?(?P<what>.+?)\s+(?:card|metric|widget|stat|figure|counter|chart)s?\s+"
                 r"(?:from\s+the\s+dashboard)?$", s) or re.match(rf"^{REMOVE_VERBS}\s+(?:the\s+)?(?P<what>.+?)\s+from\s+the\s+dashboard$", s)
    if m:
        return [ChangeOp("remove_metric", sentence, {"label": m.group("what").strip()})]

    # ---- statuses
    m = re.match(r"^(?:add|include|introduce)\s+(?:a\s+|an\s+|the\s+|new\s+)*[\"']?(?P<states>[a-z][a-z ,'\"/-]*?)[\"']?\s+"
                 r"(?:status|state|stage)(?:es|s)?\s+(?:to|for|on)\s+(?:the\s+)?(?P<ent>.+)$", s)
    m = m or re.match(r"^(?P<ent>[a-z][a-z ]+?)\s+(?:can|should|must)\s+(?:also\s+)?be\s+(?:marked|set|flagged)\s+(?:as\s+)?"
                      r"[\"']?(?P<states>[a-z][a-z ,'\"/-]*?)[\"']?$", s)
    if m:
        ents = find_entities(pm, m.group("ent"))
        if ents:
            states = [to_snake(v) for v in re.split(r"\s*(?:,|/|\bor\b|\band\b)\s*", m.group("states").replace('"', "").replace("'", ""))
                      if to_snake(v)]
            return [ChangeOp("add_state", sentence, {"entity": ents[0], "states": states})]

    # ---- removals: fields first ("remove the notes field from loans"), then records/modules
    m = re.match(rf"^{REMOVE_VERBS}\s+(?:the\s+)?(?P<what>.+?)\s+(?:from|in|on|of)\s+(?:the\s+|all\s+)?(?P<ent>[a-z][a-z ]+?)"
                 r"(?:\s+(?:records?|module|page|form|table|entity|details|profiles?))?$", s)
    if m and not re.search(r"\bdashboard\b", m.group("ent")):
        ents = find_entities(pm, m.group("ent"))
        if ents:
            # "remove X from <record>" is always about the record's fields: it never removes the record itself
            entity = _entity(pm, ents[0])
            names, missing = [], []
            for item in _split_items(m.group("what")):
                f = find_field(entity, item)
                (names.append(f.name) if f else missing.append(" ".join(_content_words(item)) or item))
            ops = [ChangeOp("remove_fields", sentence, {"entity": entity.name, "fields": names})] if names else []
            if missing:
                ops.append(ChangeOp("unresolved", sentence, {"text": f"{humanize(entity.name).capitalize()} has no field "
                                                                      f"matching {', '.join(repr(x) for x in missing)}, "
                                                                      "so nothing was removed for it."}))
            return ops
    m = re.match(rf"^{REMOVE_VERBS}\s+(?:the\s+|all\s+)?(?P<what>.+)$", s)
    if m and not set(re.findall(r"[a-z]+", m.group("what"))) & FIELD_WORDS:
        targets = []
        for item in _split_items(m.group("what")):
            ents = find_entities(pm, item, exact=True)
            if ents:
                targets += [e for e in ents if e not in targets]
        if targets:
            module = find_module(pm, m.group("what"))
            return [ChangeOp("remove_entities", sentence, {"entities": targets, "module": module.key if module else None})]

    # ---- fields on an existing record
    m = re.match(rf"^{ADD_VERBS}\s+(?:a\s+|an\s+|the\s+|new\s+)*(?P<fields>.+?)\s+(?:fields?\s+|columns?\s+|attributes?\s+)?"
                 r"(?:to|for|on|in|into)\s+(?:the\s+|each\s+|every\s+|all\s+)?(?P<ent>[a-z][a-z ]+?)"
                 r"(?:\s+(?:records?|module|page|form|table|entity|details|profiles?|list))?$", s)
    m = m or re.match(r"^(?:the\s+|each\s+|every\s+|all\s+)?(?P<ent>[a-z][a-z ]+?)\s+(?:should|must|need to|needs to|can|will)\s+"
                      r"(?:also\s+)?(?:have|include|store|track|record|show|capture|contain|get)\s+(?:a\s+|an\s+)?(?P<fields>.+)$", s)
    if m and not re.search(r"\b(module|modules|section|page|feature|system|where|which|who|that|so|when|whose|allow|let)\b",
                           m.group("fields")):
        ents = find_entities(pm, m.group("ent"))
        if ents:
            fields = [(name, values) for name, values in (_values_in(i) for i in _split_items(m.group("fields"))) if name]
            if fields and all(len(_content_words(name)) <= 4 for name, _ in fields):
                return [ChangeOp("add_fields", sentence, {"entity": ents[0], "fields": [
                    {"phrase": name, "values": values} for name, values in fields]})]
    return None


def _title(sentence: str, value: str) -> str:
    """Keep the user's capitalisation for names ("rename the app to City Library")."""
    found = re.search(re.escape(value), sentence, re.I)
    text = found.group(0) if found else value
    return text.strip(" .\"'") if any(c.isupper() for c in text) else " ".join(w.capitalize() for w in text.split())


def _role_params(pm: PMOutput, role_words: str, rest: str) -> Dict[str, Any]:
    name = to_snake(" ".join(w for w in role_words.split() if w not in {"new", "a", "an"}))
    permissions: Dict[str, List[str]] = {}
    denied: Set[str] = set()
    rest = rest.strip()
    m = re.search(r"\b(?:who|that|which)?\s*(?:can|could|may|should be able to|is able to|will|to)\s+(?P<grants>.+)$", rest)
    if m:
        grants = m.group("grants")
        split = re.split(r"\s*(?:,?\s*but\s+(?:not|cannot|can't|can not)|except(?:\s+for)?|apart from|other than)\s+", grants, maxsplit=1)
        allowed_text = split[0]
        if len(split) > 1:
            for item in _split_items(re.sub(rf"^(?:{'|'.join(VERB_ACTIONS)})\s+", "", split[1])):
                denied.update(find_entities(pm, item))
        verb = None
        for chunk in re.split(rf"\b({'|'.join(VERB_ACTIONS)})\b", allowed_text):
            chunk = chunk.strip(" ,")
            if not chunk:
                continue
            if chunk in VERB_ACTIONS:
                verb = chunk
                continue
            if verb is None:
                continue
            for item in _split_items(chunk):
                for ent in find_entities(pm, item):
                    permissions[ent] = sorted(set(permissions.get(ent, [])) | set(VERB_ACTIONS[verb]))
    return {"role": name, "permissions": permissions, "denied": sorted(denied),
            "is_admin": bool(re.search(r"\b(full access|everything|all records|administrator)\b", rest))}


# ---------------------------------------------------------------------------------------------- applying
def apply_change_ops(previous: PMOutput, ops: List[ChangeOp], request: str,
                     unresolved: Optional[List[str]] = None) -> ChangeResult:
    pm = PMOutput.model_validate(previous.model_dump())
    result = ChangeResult(pm=pm, applied=[], unresolved=list(unresolved or []), removed=set(), notes=[])
    touched_status: Set[str] = set()
    for op in ops:
        handler = _HANDLERS.get(op.kind)
        if handler is None:
            result.unresolved.append(f"“{op.sentence}” could not be applied.")
            continue
        done = handler(pm, op, result, touched_status)
        if done:
            result.applied.append((op.sentence, done))
    _refresh_workflows(pm, touched_status)
    _refresh_documentation(previous, pm, result)
    pm.source_prompt = (previous.source_prompt or "").rstrip() + "\n\nChange request:\n" + request.strip()
    return result


def _op_note(pm, op, result, _touched):
    result.notes.append(op.params["text"])
    return None


def _op_unresolved(pm, op, result, _touched):
    result.unresolved.append(op.params["text"])
    return None


def _op_unsupported(pm, op, result, _touched):
    for label in op.params.get("labels", []):
        if label not in pm.unsupported_requests:
            pm.unsupported_requests.append(label)
        result.unresolved.append(f"Not supported by the generator: {label} (“{op.sentence}”).")
    return None


def _op_theme(pm, op, result, _touched):
    done = []
    for key in ("primary_color", "sidebar_color"):
        value = op.params.get(key)
        if value and re.match(r"^#[0-9a-fA-F]{6}$", value) and pm.theme.get(key) != value:
            pm.theme[key] = value
            done.append(f"{humanize(key).capitalize()} set to {value}")
    return done


def _op_rename_project(pm, op, result, _touched):
    name = (op.params.get("name") or "").strip()[:80]
    if not name or name == pm.project_name:
        return None
    pm.project_name = name
    return [f"Application renamed to {name}"]


def _op_rename_module(pm, op, result, _touched):
    module = next((m for m in pm.module_specs if m.key == op.params.get("module")), None)
    label = (op.params.get("label") or "").strip()[:60]
    if not module or not label or module.label == label:
        return None
    old = module.label
    module.label = label
    module.name = label
    result.notes.append(f"The '{old}' module is now shown as '{label}'; its records keep their internal names so "
                        "existing data and API paths stay valid.")
    return [f"Module '{old}' renamed to '{label}'"]


def _new_field(entity: DatabaseEntity, phrase: str, values: List[str], pm: PMOutput) -> Optional[EntityField]:
    words = _content_words(phrase)
    if not words:
        return None
    target = find_entities(pm, phrase)
    if target and target[0] != entity.name and not values and len(words) <= 3:
        return EntityField(name=fk_field_name(target[0]), type="reference", references=target[0], nullable=True,
                           label=humanize(to_snake(target[0])).capitalize())
    fd = infer_field(words, to_snake(entity.name))
    if fd is None:
        return None
    ftype, enum_values = fd.type, list(fd.values)
    if values:
        ftype, enum_values = "enum", [to_snake(v) for v in values if to_snake(v)]
    name = safe_identifier(fd.name)
    if name == "status" and not enum_values:
        return None
    return EntityField(name=name, type=ftype, nullable=not fd.required, unique=fd.unique, searchable=fd.searchable,
                       enum_values=enum_values, label=fd.label or humanize(name).capitalize(), min_value=fd.min_value,
                       max_value=fd.max_value, default=enum_values[0] if enum_values else None)


def _insert_field(entity: DatabaseEntity, f: EntityField) -> None:
    tail = next((i for i, x in enumerate(entity.fields) if x.read_only and x.name in ("owner_id", "created_at")),
                len(entity.fields))
    entity.fields.insert(tail, f)


def _op_add_fields(pm, op, result, touched):
    entity = _entity(pm, op.params["entity"])
    if entity is None:
        return None
    done = []
    for item in op.params.get("fields", []):
        f = _new_field(entity, item.get("phrase", ""), item.get("values") or [], pm) if "phrase" in item else \
            _field_from_llm(item, pm, entity)
        if f is None:
            result.unresolved.append(f"Could not turn “{item.get('phrase') or item.get('name')}” into a field "
                                     f"of {humanize(entity.name)}.")
            continue
        existing = next((x for x in entity.fields if x.name == f.name), None)
        if existing is not None:
            if f.type == "enum" and f.enum_values and existing.type in ("enum", "string") and existing.enum_values != f.enum_values:
                existing.type, existing.enum_values, existing.default = "enum", f.enum_values, f.enum_values[0]
                done.append(f"{entity.name}.{f.name} now offers {', '.join(f.enum_values)}")
                if f.name == "status":
                    touched.add(entity.name)
            else:
                result.notes.append(f"{humanize(entity.name).capitalize()} already has a {f.label or f.name} field.")
            continue
        _insert_field(entity, f)
        if f.name == "status":
            touched.add(entity.name)
        kind = f"reference to {f.references}" if f.references else (
            f"{f.type}: {', '.join(f.enum_values)}" if f.enum_values else f.type)
        done.append(f"Field {entity.name}.{f.name} ({kind}) added")
    return done


def _field_from_llm(item: Dict[str, Any], pm: PMOutput, entity: DatabaseEntity) -> Optional[EntityField]:
    name = safe_identifier(str(item.get("name") or ""))
    if not name:
        return None
    ftype = str(item.get("type") or "string").lower()
    if ftype == "reference":
        target = to_pascal(singularize(str(item.get("references") or "")))
        if not _entity(pm, target) or target == entity.name:
            return None
        return EntityField(name=fk_field_name(target), type="reference", references=target, nullable=True,
                           label=humanize(to_snake(target)).capitalize())
    if ftype not in {"string", "text", "integer", "float", "decimal", "boolean", "date", "datetime", "time", "email", "enum"}:
        ftype = "string"
    values = [to_snake(v) for v in item.get("enum_values") or [] if to_snake(str(v))]
    if ftype == "enum" and not values:
        ftype = "string"
    return EntityField(name=name, type=ftype, nullable=not item.get("required", False), label=humanize(name).capitalize(),
                       enum_values=values if ftype == "enum" else [], default=values[0] if ftype == "enum" else
                       ("false" if ftype == "boolean" else None), searchable=ftype in ("string", "text", "email"))


def _op_remove_fields(pm, op, result, touched):
    entity = _entity(pm, op.params["entity"])
    if entity is None:
        return None
    done = []
    for name in op.params.get("fields", []):
        f = next((x for x in entity.fields if x.name == name and not x.read_only and not x.primary_key), None)
        if f is None:
            continue
        if sum(1 for x in entity.fields if not x.read_only and not x.primary_key and not x.hidden) <= 1:
            result.unresolved.append(f"{humanize(entity.name).capitalize()} needs at least one field; "
                                     f"{f.name} was kept.")
            continue
        entity.fields.remove(f)
        result.removed.add(f"{entity.name}.{name}")
        _drop_field_references(pm, entity, name)
        done.append(f"Field {entity.name}.{name} removed")
    return done


def _drop_field_references(pm: PMOutput, entity: DatabaseEntity, name: str) -> None:
    if entity.display_field == name:
        entity.display_field = next((f.name for f in entity.fields if f.type in ("string", "email") and not f.read_only), "id")
    pm.business_rules = [r for r in pm.business_rules if not (r.entity == entity.name and name in r.fields)
                         and not (r.entity == entity.name and name in map(str, r.params.values()))]
    pm.dashboard_metrics = [m for m in pm.dashboard_metrics if not (m.entity == entity.name and (
        m.field == name or name in map(str, m.params.values())))]
    if name == "status":
        pm.workflows = [w for w in pm.workflows if w.entity != entity.name]
    for rows in [pm.seed_records.get(entity.name, [])]:
        for row in rows:
            row.pop(name, None)


def _op_remove_entities(pm, op, result, _touched):
    remaining = [e for e in _app_entities(pm) if e.name not in op.params["entities"]]
    if not remaining:
        result.unresolved.append("The application needs at least one kind of record; nothing was removed.")
        return None
    done = []
    for name in op.params["entities"]:
        entity = _entity(pm, name)
        if entity is None:
            continue
        pm.database_entities.remove(entity)
        result.removed.add(name)
        done.append(f"{humanize(name).capitalize()} records removed")
        for other in pm.database_entities:
            for f in [f for f in other.fields if f.references == name]:
                other.fields.remove(f)
                _drop_field_references(pm, other, f.name)
                done.append(f"Field {other.name}.{f.name} removed (it pointed to {name})")
        for m in pm.module_specs:
            if name in m.entities:
                m.entities.remove(name)
        pm.workflows = [w for w in pm.workflows if w.entity != name]
        pm.business_rules = [r for r in pm.business_rules if r.entity != name and name not in map(str, r.params.values())]
        pm.dashboard_metrics = [m for m in pm.dashboard_metrics if m.entity != name and name not in map(str, m.params.values())]
        pm.role_permissions = [p for p in pm.role_permissions if p.entity != name]
        pm.seed_records.pop(name, None)
        pm.requirement_trace = [t for t in pm.requirement_trace if not t.targets or any(
            not x.split(".")[0].split(":")[0] == name for x in t.targets)]
    for m in [m for m in pm.module_specs if m.kind == "entities" and not m.entities]:
        pm.module_specs.remove(m)
        result.removed.add(f"module:{m.key}")
        done.append(f"Module '{m.label}' removed")
    return done


def _op_add_state(pm, op, result, touched):
    entity = _entity(pm, op.params["entity"])
    if entity is None:
        return None
    status = next((f for f in entity.fields if f.name == "status"), None)
    new = [s for s in op.params.get("states", []) if s]
    if not new:
        return None
    if status is None:
        status = EntityField(name="status", type="enum", nullable=False, enum_values=["open"] + [s for s in new if s != "open"],
                             label="Status", default="open")
        _insert_field(entity, status)
        added = status.enum_values
    else:
        added = [s for s in new if s not in status.enum_values]
        if not added:
            result.notes.append(f"{humanize(entity.name).capitalize()} already has the status {', '.join(new)}.")
            return None
        status.type = "enum"
        status.enum_values = list(status.enum_values) + added
        status.default = status.default or status.enum_values[0]
    touched.add(entity.name)
    return [f"{entity.name} status '{s}' added" for s in added]


def _op_add_role(pm, op, result, _touched):
    name = op.params.get("role")
    if not name or name in {"user_role", "role"}:
        return None
    if any(r.name == name for r in pm.user_roles):
        result.notes.append(f"The role '{name}' already exists; its permissions were updated.")
    else:
        pm.user_roles.append(UserRole(name=name, description=humanize(name).capitalize(),
                                      is_admin=bool(op.params.get("is_admin"))))
    grants: Dict[str, List[str]] = op.params.get("permissions") or {}
    denied = set(op.params.get("denied") or [])
    pm.role_permissions = [p for p in pm.role_permissions if p.role != name]
    lines = []
    for e in _app_entities(pm):
        if e.name in denied:
            acts: List[str] = []
        elif e.name in grants:
            acts = sorted(set(grants[e.name]) | {"read"})
        else:
            acts = ["read"]
        pm.role_permissions.append(RolePermission(role=name, entity=e.name, actions=acts))
        if e.name in grants or e.name in denied:
            lines.append(f"{e.name}: {', '.join(acts) if acts else 'no access'}")
    _refresh_user_entity(pm)
    return [f"Role '{name}' added" + (f" ({'; '.join(lines)})" if lines else " (read-only access)")]


def _op_remove_role(pm, op, result, _touched):
    name = op.params["role"]
    role = next((r for r in pm.user_roles if r.name == name), None)
    if role is None:
        return None
    if role.is_admin and sum(1 for r in pm.user_roles if r.is_admin) <= 1:
        result.unresolved.append("The administrator role cannot be removed.")
        return None
    if not role.is_admin and sum(1 for r in pm.user_roles if not r.is_admin) <= 1:
        result.unresolved.append(f"'{name}' is the only non-admin role, so it was kept.")
        return None
    pm.user_roles.remove(role)
    pm.role_permissions = [p for p in pm.role_permissions if p.role != name]
    result.removed.add(f"role:{name}")
    _refresh_user_entity(pm)
    return [f"Role '{name}' removed"]


def _refresh_user_entity(pm: PMOutput) -> None:
    from backend.agents.pm_analysis import _user_entity

    index = next((i for i, e in enumerate(pm.database_entities) if e.is_system), None)
    if index is not None:
        pm.database_entities[index] = _user_entity(pm.user_roles)


def _metric_key(m: DashboardMetric) -> Tuple:
    return (m.kind, m.entity, m.field, m.value, m.label.lower())


def _op_add_metric(pm, op, result, _touched):
    from backend.agents.spec_finalize import _metrics

    label = op.params.get("label", "").strip()
    if not label:
        return None
    trial = PMOutput.model_validate(pm.model_dump())
    trial.dashboard_metrics = list(trial.dashboard_metrics) + [DashboardMetric(id="", label=label, kind="ask")]
    before = {_metric_key(m) for m in pm.dashboard_metrics}
    before_labels = {m.label.lower() for m in pm.dashboard_metrics}
    new = [m for m in _metrics(trial) if _metric_key(m) not in before and m.label.lower() not in before_labels
           and m.kind != "ask"]
    if not new:
        same = next((m for m in pm.dashboard_metrics if m.label.lower() == label.lower()), None)
        if same:
            result.notes.append(f"The dashboard already shows '{same.label}'.")
        else:
            result.unresolved.append(f"The dashboard figure “{label}” could not be computed from the records "
                                     "the application stores; add the fields it needs first.")
        return None
    taken = {m.id for m in pm.dashboard_metrics}
    done = []
    for m in new[:2]:
        n = len(pm.dashboard_metrics) + 1
        while f"m{n}" in taken:
            n += 1
        m.id = f"m{n}"
        taken.add(m.id)
        pm.dashboard_metrics.append(m)
        done.append(f"Dashboard figure '{m.label}' added")
    return done


def _op_remove_metric(pm, op, result, _touched):
    words = set(_clean_phrase(op.params.get("label", "")))
    if not words:
        return None
    hits = [m for m in pm.dashboard_metrics if words <= set(re.findall(r"[a-z']+", m.label.lower())) or
            m.label.lower() == op.params.get("label", "").lower()]
    if not hits:
        result.unresolved.append(f"No dashboard figure matches “{op.params.get('label')}”.")
        return None
    for m in hits:
        pm.dashboard_metrics.remove(m)
        result.removed.add(f"metric:{m.label}")
    return [f"Dashboard figure '{m.label}' removed" for m in hits]


def _op_add_records(pm, op, result, _touched):
    """New records/modules: analyse the original prompt plus these sentences and take only the new records."""
    from backend.agents.pm_analysis import analyze_prompt

    sentences = op.params.get("sentences") or [op.sentence]
    text = " ".join(sentences).lower()
    try:
        candidate = analyze_prompt((pm.source_prompt or pm.description).strip() + "\n\n" + "\n".join(sentences))
    except ValueError:
        candidate = None
    existing = {e.name for e in pm.database_entities}
    new_entities: List[DatabaseEntity] = []
    if candidate is not None:
        for e in _app_entities(candidate):
            if e.name in existing:
                continue
            parts = to_snake(e.name).split("_")
            if all(re.search(rf"\b{re.escape(p)}", text) for p in parts if len(p) > 2):
                new_entities.append(e)
    if not new_entities:
        for s in sentences:
            result.unresolved.append(f"“{s}” did not describe a record, field, role, status or colour that "
                                     "FORGE AI could add.")
        return None
    names = {e.name for e in new_entities}
    allowed = existing | names
    done = []
    for e in new_entities:
        e.fields = [f for f in e.fields if not f.references or f.references in allowed]
        pm.database_entities.append(e)
        refs = [f.references for f in e.fields if f.references and f.references != "User"]
        done.append(f"{humanize(e.name).capitalize()} records added ({sum(1 for f in e.fields if not f.read_only)} fields"
                    + (f", linked to {', '.join(refs)}" if refs else "") + ")")
    # modules: the candidate's module when it only holds new records, otherwise a module of their own
    placed: Set[str] = set()
    keys = {m.key for m in pm.module_specs}
    for m in candidate.module_specs:
        ents = [x for x in m.entities if x in names and x not in placed]
        if m.kind == "entities" and ents and set(m.entities) <= names and m.key not in keys:
            pm.module_specs.insert(_module_slot(pm), ModuleSpec(**{**m.model_dump(), "entities": ents}))
            placed.update(ents)
            keys.add(m.key)
            done.append(f"Module '{m.label}' added")
    for e in new_entities:
        if e.name not in placed:
            label = humanize(pluralize(to_snake(e.name))).capitalize()
            key = to_snake(e.name)
            while key in keys:
                key += "_records"
            pm.module_specs.insert(_module_slot(pm), ModuleSpec(key=key, name=label, label=label, entities=[e.name]))
            keys.add(key)
            done.append(f"Module '{label}' added")
    # workflows, rules, metrics, permissions and seed records of the new records (as a fresh build would make them)
    pm.workflows += [w for w in candidate.workflows if w.entity in names]
    rule_ids = {r.id for r in pm.business_rules}
    for r in candidate.business_rules:
        if r.entity in names and all(str(v) in allowed or not str(v)[:1].isupper() for v in r.params.values()):
            r.id = _unique_id("rule_", rule_ids)
            pm.business_rules.append(r)
    taken = {m.id for m in pm.dashboard_metrics}
    for m in candidate.dashboard_metrics:
        if m.entity in names and all(str(v) in allowed or not str(v)[:1].isupper() for v in m.params.values()):
            m.id = _unique_id("m", taken)
            pm.dashboard_metrics.insert(_metric_slot(pm), m)
            done.append(f"Dashboard figure '{m.label}' added")
    explicit = {(p.role, p.entity): p for p in candidate.role_permissions}
    for role in pm.user_roles:
        for e in new_entities:
            if (role.name, e.name) in explicit and not role.is_admin:
                acts = explicit[(role.name, e.name)].actions
            elif role.is_admin or e.access == "owner":
                acts = list(CRUD)
            elif e.access == "admin_managed":
                acts = ["read"]
            else:
                acts = ["create", "read", "update"]
            pm.role_permissions.append(RolePermission(role=role.name, entity=e.name, actions=sorted(set(acts) | {"read"})))
    for name in names:
        if candidate.seed_records.get(name):
            pm.seed_records[name] = candidate.seed_records[name]
    for t in candidate.requirement_trace:
        if t.targets and any(x.split(".")[0].split(":")[0] in names for x in t.targets):
            pm.requirement_trace.append(TraceItem(**{**t.model_dump(), "id": f"REQ-C{len(pm.requirement_trace) + 1:03d}"}))
    pm.unsupported_requests += [u for u in candidate.unsupported_requests if u not in pm.unsupported_requests
                                and re.search(re.escape(u.split(" ")[0].lower()), text)]
    return done


def _unique_id(prefix: str, taken: Set[str]) -> str:
    n = len(taken) + 1
    while f"{prefix}{n}" in taken:
        n += 1
    taken.add(f"{prefix}{n}")
    return f"{prefix}{n}"


def _module_slot(pm: PMOutput) -> int:
    """New modules go after the existing record modules (before Reports)."""
    return next((i for i, m in enumerate(pm.module_specs) if m.kind != "entities"), len(pm.module_specs))


def _metric_slot(pm: PMOutput) -> int:
    return next((i for i, m in enumerate(pm.dashboard_metrics) if m.kind in ("recent",)), len(pm.dashboard_metrics))


_HANDLERS = {
    "note": _op_note, "unresolved": _op_unresolved, "unsupported": _op_unsupported, "theme": _op_theme, "rename_project": _op_rename_project,
    "rename_module": _op_rename_module, "add_fields": _op_add_fields, "remove_fields": _op_remove_fields,
    "remove_entities": _op_remove_entities, "add_state": _op_add_state, "add_role": _op_add_role,
    "remove_role": _op_remove_role, "add_metric": _op_add_metric, "remove_metric": _op_remove_metric,
    "add_records": _op_add_records,
}


def _refresh_workflows(pm: PMOutput, entities: Set[str]) -> None:
    """Recompute the workflow of records whose statuses changed (others are kept exactly as they were)."""
    if not entities:
        return
    from backend.agents.spec_finalize import _workflows

    trial = PMOutput.model_validate(pm.model_dump())
    trial.workflows = [w for w in trial.workflows if w.entity not in entities]
    fresh = {w.entity: w for w in _workflows(trial) if w.entity in entities}
    kept = [w for w in pm.workflows if w.entity not in entities]
    pm.workflows = kept + [fresh[e] for e in sorted(fresh)]


def _refresh_documentation(previous: PMOutput, pm: PMOutput, result: ChangeResult) -> None:
    """Features, module list and functional requirements follow the changed modules; nothing else is rewritten."""
    from backend.agents.pm_analysis import _derive_documentation

    gone = [humanize(to_snake(x)).lower() for x in result.removed if ":" not in x and "." not in x]
    gone += [x.split(":", 1)[1].replace("_", " ") for x in result.removed if x.startswith("module:")]
    pm.features = [f for f in pm.features if not any(re.search(rf"\b{re.escape(g)}", f.lower()) for g in gone)]
    keep_frs = [r for r in pm.functional_requirements if not any(re.search(rf"\b{re.escape(g)}", r.title.lower()) for g in gone)]
    before = set(pm.features)
    _derive_documentation(pm)
    added = [f for f in pm.features if f not in before and f not in previous.features]
    ids = {r.id for r in keep_frs}
    for feat in added:
        n = len(ids) + 1
        while f"FR-{n:03d}" in ids:
            n += 1
        ids.add(f"FR-{n:03d}")
        keep_frs.append(Requirement(id=f"FR-{n:03d}", title=feat, description=feat, priority="must"))
    pm.functional_requirements = keep_frs


def apply_change_request(previous: PMOutput, request: str) -> ChangeResult:
    """Deterministic refinement: parse the request and apply it to a copy of ``previous``."""
    ops, unresolved = parse_change_request(previous, request)
    return apply_change_ops(previous, ops, request, unresolved)
