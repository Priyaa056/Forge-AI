"""Final pass over a normalized specification (both LLM and deterministic output).

Resolves the prompt's wording into concrete, checkable items on the final schema:
workflows (from status fields), business rules (unique-together, date order, resource allocation,
computed balances, stock/expiry/overdue alerts), dashboard metrics and seed records. Anything that
cannot be resolved is reported in ``ambiguities`` instead of being silently invented.
"""

import re
from typing import Dict, List, Optional, Set, Tuple

from backend.agents import attribute_lexicon as lex
from backend.codegen.naming import humanize, pluralize, singularize, to_snake
from backend.schemas.pm_schema import (
    BusinessRule,
    DashboardMetric,
    DatabaseEntity,
    EntityField,
    PMOutput,
    TraceItem,
    WorkflowSpec,
    WorkflowTransition,
)

REVERSE_VERBS: Dict[str, str] = {}
for _verb, _state in lex.VERB_STATES.items():
    REVERSE_VERBS.setdefault(_state, _verb)  # first (most natural) verb wins: complete -> completed
MARK_STATES = {"paid", "available", "occupied", "reserved", "maintenance", "active", "inactive", "in_use", "unpaid",
               "partially_paid", "present", "absent", "late", "excused", "open", "on_trip", "off_duty"}
MONEY_FIELDS = re.compile(r"(amount|total|price|cost|fee|revenue|paid|charge|fare|salary|value)$")
DATE_KINDS = {"date", "datetime"}
ALIASES = {"bill": "invoice", "bills": "invoice", "visit": "appointment", "revenue": None}


def _app_entities(pm: PMOutput) -> Dict[str, DatabaseEntity]:
    return {e.name: e for e in pm.database_entities if not e.is_system}


def _find_entity(pm: PMOutput, word: str) -> Optional[DatabaseEntity]:
    word = singularize(word.lower().strip())
    word = ALIASES.get(word, word) or word
    ents = _app_entities(pm)
    for e in ents.values():
        snake = to_snake(e.name)
        if word in {snake, snake.replace("_", " "), snake.split("_")[-1], humanize(snake).lower()}:
            return e
    return None


def _field(e: DatabaseEntity, *patterns: str, kinds: Optional[set] = None) -> Optional[EntityField]:
    for p in patterns:
        for f in e.fields:
            if (kinds is None or f.type in kinds) and re.search(p, f.name):
                return f
    return None


def _date_field(e: DatabaseEntity) -> Optional[EntityField]:
    preferred = _field(e, r"(scheduled|appointment|start|admitted|booking|trip|service|fill|exam|lesson|attendance|harvest|inspection|issued|order|sale|paid|record|reported|requested)_?(date|on|at|time)?$", kinds=DATE_KINDS)
    return preferred or next((f for f in e.fields if f.type in DATE_KINDS and f.name != "created_at"), None)


def _status(e: DatabaseEntity) -> Optional[EntityField]:
    return next((f for f in e.fields if f.name == "status" and f.type == "enum" and len(f.enum_values) >= 2), None)


def _action(state: str) -> Tuple[str, str]:
    verb = REVERSE_VERBS.get(state)
    if verb and state not in MARK_STATES:
        return verb, humanize(verb).capitalize()
    return f"mark_{state}", f"Mark {humanize(state).lower()}"


def _workflows(pm: PMOutput) -> List[WorkflowSpec]:
    existing = {w.entity for w in pm.workflows}
    flows = [w for w in pm.workflows if w.entity in _app_entities(pm)]
    for e in _app_entities(pm).values():
        st = _status(e)
        if not st or e.name in existing:
            continue
        states = list(st.enum_values)
        resource = bool(set(states) & lex.AVAILABLE_STATES) and bool(set(states) & lex.OCCUPIED_STATES | {"maintenance"})
        terminal = [s for s in states if s in lex.TERMINAL_STATES] if not resource else []
        transitions = []
        for s in states[1:] if not resource else states:
            frm = [x for x in states if x != s and x not in terminal]
            if s in lex.CANCEL_STATES:
                frm = [x for x in states if x not in terminal and x != s]
            if not frm:
                continue
            action, label = _action(s)
            transitions.append(WorkflowTransition(action=action, label=label, from_states=frm, to_state=s))
        if transitions:
            flows.append(WorkflowSpec(entity=e.name, field="status", states=states, initial=states[0], terminal=terminal,
                                      transitions=transitions, source=f"{e.name} statuses: {', '.join(states)}"))
    return flows


def _resolve_rules(pm: PMOutput) -> List[BusinessRule]:
    ents = _app_entities(pm)
    rules: List[BusinessRule] = []
    notes = pm.ambiguities
    explicit_resources: Set[str] = set()  # "update bed availability after admission or discharge"

    def add(rule: BusinessRule):
        key = (rule.kind, rule.entity, tuple(rule.fields))
        if key not in {(r.kind, r.entity, tuple(r.fields)) for r in rules}:
            rule.id = f"rule_{len(rules) + 1}"
            rules.append(rule)

    for r in pm.business_rules:
        if r.kind == "unique_together":
            e = ents.get(r.entity)
            if not e:
                continue
            cols: List[str] = []
            for phrase in r.fields:
                words = phrase.lower().split()
                candidates = {f"{to_snake(singularize(w))}_id" for w in words} | {f"{to_snake(singularize(phrase.lower()))}_id"}
                ref = next((f for f in e.fields if f.type == "reference" and f.name in candidates), None)
                if ref:
                    cols.append(ref.name)
                    continue
                if any(w in {"slot", "time", "date", "datetime", "day", "period"} for w in words):
                    cols.extend(f.name for f in e.fields if f.type in {"date", "datetime", "time"} and f.name != "created_at")
                    continue
                match = next((f for f in e.fields if f.name in {to_snake(phrase), to_snake(singularize(phrase))}), None)
                if match:
                    cols.append(match.name)
            cols = list(dict.fromkeys(cols))
            if len(cols) >= 2:
                add(BusinessRule(id="", kind="unique_together", entity=e.name, fields=cols, description=r.description, source=r.source))
            else:
                notes.append(f"Could not map rule '{r.description[:80]}' to fields of {e.name}.")
        elif r.kind == "low_stock":
            target = ents.get(r.entity)
            candidates = ([target] if target else []) + list(ents.values())
            for e in candidates:
                f = e and _field(e, r"^(quantity|stock|qty|units|quantity_in_stock|copies_available)$", kinds={"integer"})
                if f:
                    add(BusinessRule(id="", kind="low_stock", entity=e.name, fields=[f.name], params={"threshold": 10},
                                     description=r.description or f"Low stock when {f.name} <= 10", source=r.source))
                    break
        elif r.kind == "expiry":
            target = ents.get(r.entity)
            candidates = ([target] if target else []) + list(ents.values())
            for e in candidates:
                f = e and _field(e, r"expir", kinds=DATE_KINDS)
                if f:
                    add(BusinessRule(id="", kind="expiry", entity=e.name, fields=[f.name], params={"warning_days": 30},
                                     description=r.description, source=r.source))
                    break
        elif r.kind == "overdue":
            for e in ([ents[r.entity]] if r.entity in ents else []) + list(ents.values()):
                f = _field(e, r"^(due_date|due_on|deadline|end_date)$", kinds=DATE_KINDS)
                if f:
                    add(BusinessRule(id="", kind="overdue", entity=e.name, fields=[f.name], description=r.description, source=r.source))
                    break
        elif r.kind == "allocation" and not r.entity:
            resource = r.params.get("resource")
            if resource in ents:
                explicit_resources.add(resource)
            else:
                notes.append(f"Could not map rule '{r.description[:80]}' to a resource entity.")
        elif r.kind in {"date_order", "computed", "allocation"}:
            if r.entity in ents:
                add(r)

    # generic: end date must not precede start date
    pairs = [("start", "end"), ("admitted", "discharged"), ("admission", "discharge"), ("borrowed", "returned"),
             ("borrowed", "due"), ("check_in", "check_out"), ("departure", "arrival"), ("start_time", "end_time"),
             ("shipped", "delivered"), ("issued", "due"), ("fill", "next")]
    for e in ents.values():
        due = next((f for f in e.fields if f.name in ("due_date", "due_on") and f.type in DATE_KINDS), None)
        start = next((f for f in e.fields if f.type == (due.type if due else None) and f is not due
                      and f.name != "created_at" and not f.name.startswith(("return", "end", "expir", "next"))), None)
        if due and start:  # "loan date ... due date": the due date cannot precede the start
            add(BusinessRule(id="", kind="date_order", entity=e.name, fields=[start.name, due.name],
                             description=f"{humanize(due.name).capitalize()} cannot be before {humanize(start.name).lower()}"))
        dates = [f for f in e.fields if f.type in DATE_KINDS | {"time"} and f.name != "created_at"]
        for a, b in pairs:
            fa = next((f for f in dates if f.name.startswith(a)), None)
            fb = next((f for f in dates if f.name.startswith(b)), None)
            if fa and fb and fa.name != fb.name and fa.type == fb.type:
                add(BusinessRule(id="", kind="date_order", entity=e.name, fields=[fa.name, fb.name],
                                 description=f"{humanize(fb.name).capitalize()} cannot be before {humanize(fa.name).lower()}"))
    # generic: computed balance = total - paid
    for e in ents.values():
        total = _field(e, r"^(total_amount|total|amount_due|total_cost|grand_total)$", kinds={"decimal"})
        paid = _field(e, r"^(paid_amount|amount_paid|paid)$", kinds={"decimal"})
        balance = _field(e, r"(balance|outstanding|pending_amount)", kinds={"decimal"})
        if total and paid:
            if not balance:
                balance = EntityField(name="balance", type="decimal", label="Balance", read_only=True, nullable=True)
                e.fields.insert(len(e.fields) - 1, balance)
            balance.read_only = True
            add(BusinessRule(id="", kind="computed", entity=e.name, fields=[balance.name, total.name, paid.name],
                             params={"expression": f"{total.name} - {paid.name}"},
                             description=f"{humanize(balance.name).capitalize()} = {humanize(total.name)} - {humanize(paid.name)}"))
    # generic: total = quantity x price when a record has both but no total ("crop quantities and prices")
    for e in ents.values():
        qty = _field(e, r"(^|_)quantity$", kinds={"integer", "float", "decimal"})
        price = _field(e, r"(^|_)(unit_)?price$", kinds={"decimal", "float"})
        if qty and price and not _field(e, r"^(total_amount|total|amount)$", kinds={"decimal"}):
            total = EntityField(name="total_amount", type="decimal", label="Total amount", read_only=True, nullable=True)
            e.fields.insert(len(e.fields) - 1, total)
            add(BusinessRule(id="", kind="computed", entity=e.name, fields=["total_amount", qty.name, price.name],
                             params={"expression": f"{qty.name} * {price.name}", "op": "multiply"},
                             description=f"Total amount = {humanize(qty.name)} x {humanize(price.name)}"))
    # generic: a record with a lifecycle that references a resource with available/occupied states
    # allocates it while open and releases it in a terminal state ("admission" -> bed, "trip" -> vehicle).
    for e in ents.values():
        st = _status(e)
        for f in e.fields:
            if f.type != "reference" or not f.references or f.references not in ents:
                continue
            res = ents[f.references]
            rst = _status(res)
            if not rst:
                continue
            avail = next((s for s in rst.enum_values if s in lex.AVAILABLE_STATES), None)
            own_state = to_snake(e.name).split("_")[-1]
            own_like = next((s for s in rst.enum_values if s != avail and len(own_state) >= 5
                             and s.startswith(own_state[:5])), None)  # reservation -> reserved
            occ = own_state if own_state in rst.enum_values and own_state != avail else own_like or next(
                (s for s in rst.enum_values if s in lex.OCCUPIED_STATES), None)
            if not avail or not occ or e.name == res.name:
                continue
            release = [s for s in (st.enum_values if st else []) if s in lex.TERMINAL_STATES]
            if not release and not (res.name in explicit_resources and not st):
                continue  # no lifecycle to release the resource (e.g. fuel records) unless the prompt asked
            # allocate only the most specific resource: an admission takes a bed, not the bed's whole room
            if any(g.type == "reference" and g.references in ents and g.references != res.name
                   and any(h.type == "reference" and h.references == res.name for h in ents[g.references].fields)
                   and _status(ents[g.references]) for g in e.fields):
                continue
            add(BusinessRule(id="", kind="allocation", entity=e.name, fields=[f.name],
                             params={"resource": res.name, "available": avail, "occupied": occ, "release_states": release},
                             description=f"Creating a {humanize(to_snake(e.name))} marks the {humanize(to_snake(res.name))} "
                                         f"{occ.replace('_', ' ')}; it becomes {avail} again when the "
                                         f"{humanize(to_snake(e.name))} is {'/'.join(release) or 'deleted'}."))
    return rules


ACTIVE_WORDS = {"active", "current", "currently", "employed", "working", "ongoing", "operational", "running"}


def _money_source(pm: PMOutput, ents: Dict[str, DatabaseEntity], words: List[str], side: str):
    """(entity, money field, date field) for income ("sales revenue") or expense ("monthly expenses")."""
    order = ["sale", "payment", "invoice", "order", "transaction", "income"] if side == "income" else         ["expense", "cost", "spend", "purchase", "bill"]
    mentioned = {singularize(w) for w in words}
    candidates = []
    for e in ents.values():
        snake = to_snake(e.name)
        money = _field(e, r"^total_amount$", r"^amount$", r"^paid_amount$", r"^total$", r"^price$", kinds={"decimal"})
        date = _date_field(e)
        kind_rank = next((i for i, k in enumerate(order) if k in snake.split("_")), None)
        if money and date and kind_rank is not None:
            candidates.append((0 if set(snake.split("_")) & mentioned else 1, kind_rank, len(snake), e, money, date))
    candidates.sort(key=lambda c: c[:3])
    candidates = [c[2:] for c in candidates]
    return candidates[0][1:] if candidates else None


def _metrics(pm: PMOutput) -> List[DashboardMetric]:
    ents = _app_entities(pm)
    metrics: List[DashboardMetric] = []
    used = set()

    def add(m: DashboardMetric):
        key = (m.kind, m.entity, m.field, m.value)
        if key in used or m.label.lower() in used:
            return  # e.g. the prompt's "overdue loans" already covers the default overdue alert
        used.add(key)
        used.add(m.label.lower())
        m.id = f"m{len(metrics) + 1}"
        metrics.append(m)

    module_order = {e: i for i, m in enumerate(pm.module_specs) for e in m.entities}
    asks = [m.label for m in pm.dashboard_metrics if m.kind == "ask"]
    concrete = [m for m in pm.dashboard_metrics if m.kind != "ask"]
    for m in concrete:
        if m.entity in ents:
            add(m)
    status_index = {}
    for e in ents.values():
        st = _status(e)
        if st:
            for v in st.enum_values:
                status_index.setdefault(v, []).append(e)
    for phrase in asks:
        low = phrase.lower().strip()
        words = re.findall(r"[a-z']+", low)
        if not words:
            continue
        label = phrase.strip().capitalize()
        noun = words[-1]
        if re.search(r"\b(recent|latest)\b", low):
            add(DashboardMetric(id="", label="Recent activity", kind="recent"))
            continue
        if re.search(r"\b(deadlines?|due dates?|due soon)\b", low):
            due = [(e, f) for e in ents.values() for f in [_field(e, r"^(due_date|deadline)$", kinds=DATE_KINDS)] if f]
            due = due or [(e, f) for e in ents.values() for f in [_field(e, r"^end_date$", kinds=DATE_KINDS)] if f]
            for e, f in due[:2]:
                add(DashboardMetric(id="", label=f"Upcoming {humanize(to_snake(e.name)).lower()} deadlines", kind="upcoming",
                                    entity=e.name, field=f.name))
            if due:
                continue
        if re.search(r"\bprogress\b", low):
            prog = next(((e, f) for e in ents.values() for f in e.fields if f.name == "progress" and f.type == "integer"), None)
            if prog:
                add(DashboardMetric(id="", label=f"Average {humanize(to_snake(prog[0].name)).lower()} progress", kind="average",
                                    entity=prog[0].name, field="progress"))
                continue
        if re.search(r"\bprofit\b|\bnet (?:income|result)\b", low):
            income, spend = _money_source(pm, ents, words, "income"), _money_source(pm, ents, words, "expense")
            if income and spend:
                add(DashboardMetric(id="", label="Profit and loss" if "loss" in low else label, kind="net",
                                    entity=income[0].name, field=income[1].name,
                                    params={"date_field": income[2].name, "minus_entity": spend[0].name,
                                            "minus_field": spend[1].name, "minus_date_field": spend[2].name}))
                continue
        if words == ["loss"]:
            continue  # "profit and loss" was split in two
        if re.search(r"\b(expenses?|costs?|spending|expenditures?)\b", low) and not re.search(r"\b(chart|trend|graph)\b", low):
            spend = _money_source(pm, ents, words, "expense")
            if spend:
                add(DashboardMetric(id="", label=label, kind="sum_month" if "month" in low else "sum", entity=spend[0].name,
                                    field=spend[1].name, params={"date_field": spend[2].name}))
                continue
        if re.search(r"\b(land|area|acreage|acres|hectares)\b", low):
            area = next(((e, f) for e in sorted(ents.values(), key=lambda x: module_order.get(x.name, 99))
                         for f in e.fields if f.type in ("float", "decimal", "integer")
                         and re.search(r"(^|_)(area|size|acreage|acres|hectares|land_area)$", f.name)), None)
            if area:
                add(DashboardMetric(id="", label=label, kind="sum", entity=area[0].name, field=area[1].name))
                continue
        if re.search(r"\b(revenue|income|earnings|sales total|turnover)\b", low):
            preferred = _money_source(pm, ents, words, "income")
            if preferred:
                kind = "sum_month" if "month" in low else "sum"
                add(DashboardMetric(id="", label=label, kind=kind, entity=preferred[0].name, field=preferred[1].name,
                                    params={"date_field": preferred[2].name}))
                continue
            money = None
            for e in ents.values():
                f = _field(e, r"^(amount|paid_amount|total_amount|total|price)$", kinds={"decimal"})
                d = _date_field(e)
                if f and d and re.search(r"(payment|invoice|order|sale|transaction|bill)", to_snake(e.name)):
                    money = (e, f, d)
                    break
            if not money:
                money = next(((e, f, _date_field(e)) for e in ents.values()
                              for f in [_field(e, r"^(amount|paid_amount|total_amount)$", kinds={"decimal"})] if f and _date_field(e)), None)
            if money:
                kind = "sum_month" if "month" in low else "sum"
                add(DashboardMetric(id="", label=label, kind=kind, entity=money[0].name, field=money[1].name,
                                    params={"date_field": money[2].name}))
                continue
        if re.search(r"\b(trend|trends|chart|charts|graph|over time)\b", low):
            target = next((e for w in reversed(words) for e in [_find_entity(pm, w)] if e), None)
            if target and _date_field(target):
                add(DashboardMetric(id="", label=label, kind="trend", entity=target.name,
                                    params={"date_field": _date_field(target).name}))
                continue
        wise = re.search(r"\b([a-z]+)[- ]wise\s+([a-z]+)", low)
        if wise:  # "farm-wise crop distribution": crops grouped by farm (directly or through their field)
            group, subject = _find_entity(pm, wise.group(1)), _find_entity(pm, wise.group(2))
            if group and subject:
                direct = next((f for f in subject.fields if f.type == "reference" and f.references == group.name), None)
                if direct:
                    add(DashboardMetric(id="", label=label, kind="breakdown", entity=subject.name, field=direct.name))
                    continue
                for via in subject.fields:
                    middle = ents.get(via.references) if via.type == "reference" else None
                    hop = middle and next((f for f in middle.fields if f.type == "reference" and f.references == group.name), None)
                    if hop:
                        add(DashboardMetric(id="", label=label, kind="breakdown", entity=subject.name, field=via.name,
                                            params={"through": middle.name, "group_field": hop.name, "group_entity": group.name}))
                        break
                else:
                    hop = None
                if hop:
                    continue
        if re.search(r"\b(statistics|stats|breakdown|distribution|by)\b", low):
            target = next((e for w in words for e in [_find_entity(pm, w)] if e), None)
            by = re.search(r"\bby\s+([a-z ]+)$", low)
            by_field = target and by and next((f for f in target.fields if f.name in (
                to_snake(by.group(1)), to_snake(singularize(by.group(1))), f"{to_snake(singularize(by.group(1)))}_id")), None)
            if by_field:
                add(DashboardMetric(id="", label=label, kind="breakdown", entity=target.name, field=by_field.name))
                continue
            if target:
                children = [c for c in ents.values() if any(f.type == "reference" and f.references == target.name
                                                            for f in c.fields)]
                children.sort(key=lambda c: module_order.get(c.name, 99))
                child = children[0] if children else None
                if child:
                    fk = next(f.name for f in child.fields if f.type == "reference" and f.references == target.name)
                    add(DashboardMetric(id="", label=label, kind="breakdown", entity=child.name, field=fk))
                    continue
                if _status(target):
                    add(DashboardMetric(id="", label=label, kind="breakdown", entity=target.name, field="status"))
                    continue
        if re.search(r"\btoday'?s?\b|\btoday\b", low):
            target = next((e for w in reversed(words) for e in [_find_entity(pm, w)] if e), None)
            if target and _date_field(target):
                add(DashboardMetric(id="", label=label, kind="count_today", entity=target.name, field=_date_field(target).name))
                continue
        if re.search(r"\bupcoming\b|\bnext\b|\bscheduled\b", low):
            subject = singularize(words[-1])
            planned = next(((e, f) for e in ents.values() for f in e.fields if f.type in DATE_KINDS and re.search(
                rf"^(expected|planned|next|scheduled|estimated)_{re.escape(subject)}", f.name)), None)
            if planned:  # "upcoming harvests" -> crops by expected harvest date
                add(DashboardMetric(id="", label=label, kind="upcoming", entity=planned[0].name, field=planned[1].name))
                continue
            target = next((e for w in reversed(words) for e in [_find_entity(pm, w)] if e), None)
            if target and _date_field(target):
                add(DashboardMetric(id="", label=label, kind="upcoming", entity=target.name, field=_date_field(target).name))
                continue
        # a state named inside the phrase: "equipment in use", "workers currently employed"
        target = next((e for w in words for e in [_find_entity(pm, w)] if e), None)
        st = target and _status(target)
        if st:
            named = next((v for v in sorted(st.enum_values, key=len, reverse=True)
                          if re.search(rf"\b{re.escape(v.replace('_', ' '))}\b", low)), None)
            if named is None and set(words) & ACTIVE_WORDS and "active" in st.enum_values:
                named = "active"
            if named and not (len(words) == 2 and words[0] == named):
                add(DashboardMetric(id="", label=label, kind="count_where", entity=target.name, field="status", value=named))
                continue
        # "<state> <entities>" e.g. "available beds", "admitted patients", "pending bills"
        if len(words) >= 2:
            adjective = to_snake(" ".join(words[:-1]))
            target = _find_entity(pm, noun)
            if target and adjective in {"pending", "open", "unpaid", "outstanding", "active", "current"} and _status(target) \
                    and adjective not in _status(target).enum_values:
                st = _status(target)
                values = [s for s in st.enum_values if s not in lex.TERMINAL_STATES] or st.enum_values[:1]
                if adjective in {"unpaid", "outstanding", "pending"} and "paid" in st.enum_values:
                    values = [s for s in st.enum_values if s != "paid"]
                add(DashboardMetric(id="", label=label, kind="count_where", entity=target.name, field="status",
                                    value=",".join(values)))
                continue
            if adjective in status_index:
                holder = next((e for e in status_index[adjective] if target is None or e.name == target.name), None)
                holder = holder or next((e for e in status_index[adjective] if target and any(
                    f.type == "reference" and f.references == target.name for f in e.fields)), None)
                holder = holder or status_index[adjective][0]
                add(DashboardMetric(id="", label=label, kind="count_where", entity=holder.name, field="status", value=adjective))
                continue
            if target and adjective in {"pending", "open", "unpaid", "outstanding", "active", "current"} and _status(target):
                st = _status(target)
                terminal = [s for s in st.enum_values if s in lex.TERMINAL_STATES]
                values = [s for s in st.enum_values if s not in terminal] or st.enum_values[:1]
                if adjective in {"unpaid", "outstanding"} and "paid" in st.enum_values:
                    values = [s for s in st.enum_values if s != "paid"]
                add(DashboardMetric(id="", label=label, kind="count_where", entity=target.name, field="status",
                                    value=",".join(values)))
                continue
            if words[0] in {"low"} or "stock" in words:
                rule = next((r for r in pm.business_rules if r.kind == "low_stock"), None)
                if rule:
                    add(DashboardMetric(id="", label=label, kind="alert", entity=rule.entity, field=rule.fields[0],
                                        params={"rule": "low_stock", "threshold": rule.params.get("threshold", 10)}))
                    continue
            if words[0] in {"expired", "expiring"}:
                rule = next((r for r in pm.business_rules if r.kind == "expiry"), None)
                if rule:
                    add(DashboardMetric(id="", label=label, kind="alert", entity=rule.entity, field=rule.fields[0],
                                        params={"rule": "expiry", "warning_days": 30}))
                    continue
            if words[0] in {"overdue", "late"}:
                rule = next((r for r in pm.business_rules if r.kind == "overdue" and (
                    target is None or r.entity == target.name)), None)
                if rule:
                    add(DashboardMetric(id="", label=label, kind="alert", entity=rule.entity, field=rule.fields[0],
                                        params={"rule": "overdue"}))
                    continue
        target = _find_entity(pm, noun) or next((e for w in words for e in [_find_entity(pm, w)] if e), None)
        generic_count = len(words) == 1 or (len(words) == 2 and words[0] in {"all", "total", "registered", "number"})
        if target and (re.search(r"\b(total|count|number|all)\b", low) or generic_count):
            add(DashboardMetric(id="", label=label if "total" in low or "count" in low else f"Total {humanize(pluralize(to_snake(target.name))).lower()}",
                                kind="count", entity=target.name))
            continue
        if target and words[-1] in {"deadline", "deadlines", "progress"}:
            continue
        pm.ambiguities.append(f"Dashboard request '{phrase.strip()}' could not be mapped to data and was not added.")

    # always useful, generic metrics derived from the schema
    if not any(m.kind == "count" for m in metrics):
        for e in list(ents.values())[:6]:
            add(DashboardMetric(id="", label=f"Total {humanize(pluralize(to_snake(e.name))).lower()}", kind="count", entity=e.name))
    for r in pm.business_rules:
        if r.kind in {"low_stock", "expiry", "overdue"}:
            plural = humanize(pluralize(to_snake(r.entity))).lower()
            label = {"low_stock": f"Low stock {plural}", "expiry": f"Expired / expiring {plural}",
                     "overdue": f"Overdue {plural}"}[r.kind]
            add(DashboardMetric(id="", label=label, kind="alert", entity=r.entity, field=r.fields[0],
                                params={"rule": r.kind, **r.params}))
    for w in pm.workflows[:3]:
        add(DashboardMetric(id="", label=f"{humanize(pluralize(to_snake(w.entity))).capitalize()} by status", kind="breakdown",
                            entity=w.entity, field=w.field))
    if not any(m.kind == "recent" for m in metrics):
        add(DashboardMetric(id="", label="Recent activity", kind="recent"))
    return metrics


def _seeds(pm: PMOutput) -> Dict[str, List[Dict]]:
    ents = _app_entities(pm)
    out: Dict[str, List[Dict]] = {}
    for name, rows in pm.seed_records.items():
        e = ents.get(name)
        if not e:
            continue
        display = e.display_field or next((f.name for f in e.fields if f.type == "string"), None)
        resolved = []
        for row in rows:
            row = dict(row)
            if "_display" in row and display:
                row[display] = row.pop("_display")
            row = {k: v for k, v in row.items() if any(f.name == k for f in e.fields)}
            if row:
                resolved.append(row)
        if resolved:
            out[name] = resolved
    return out


def finalize_spec(pm: PMOutput) -> PMOutput:
    pm.business_rules = _resolve_rules(pm)
    pm.workflows = _workflows(pm)
    pm.dashboard_metrics = _metrics(pm)
    pm.seed_records = _seeds(pm)
    traced = {t.text for t in pm.requirement_trace}
    for w in pm.workflows:
        text = w.source or f"{w.entity} workflow"
        if text not in traced:
            pm.requirement_trace.append(TraceItem(id=f"REQ-W{len(pm.requirement_trace) + 1:03d}", text=text, kind="workflow",
                                                  targets=[f"{w.entity}.{t.action}" for t in w.transitions]))
    for r in pm.business_rules:
        pm.requirement_trace.append(TraceItem(id=f"REQ-R{len(pm.requirement_trace) + 1:03d}", text=r.description[:300],
                                              kind="rule", targets=[f"{r.entity}:{r.kind}"]))
    if not pm.purpose:
        ordered = [e for m in pm.module_specs for e in m.entities if e in _app_entities(pm)]
        ordered += [e for e in _app_entities(pm) if e not in ordered]
        names = [humanize(pluralize(to_snake(e))).lower() for e in dict.fromkeys(ordered)]
        users = [humanize(pluralize(r.name)).lower() for r in pm.user_roles if not r.is_admin and r.name != "user"]
        listed = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]
        people = (", ".join(users[:-1]) + " and " + users[-1]) if len(users) > 1 else (users[0] if users else "")
        pm.purpose = f"Manage {listed}" + (f" for {people}" if people else "") + "."
    pm.ambiguities = list(dict.fromkeys(pm.ambiguities))
    return pm
