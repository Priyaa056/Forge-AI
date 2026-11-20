"""Iterative refinement, PM side: change requests become precise edits of the existing specification."""

import json

import pytest

from backend.agents.change_plan import build_change_plan, diff_specs, preserve_existing
from backend.agents.change_request import apply_change_request, split_request
from backend.agents.pm_agent import PMAgent, RefinementNoChange
from backend.agents.pm_analysis import PromptValidationError, analyze_prompt
from backend.schemas.pm_schema import PMOutput

LIBRARY = ("Build a library management system with members, books, loans with due dates, fines for late returns "
           "and an admin dashboard showing overdue loans.")


@pytest.fixture(scope="module")
def library() -> PMOutput:
    return analyze_prompt(LIBRARY)


def entities(pm):
    return {e.name: {f.name: f for f in e.fields} for e in pm.database_entities if not e.is_system}


def unchanged_except(before: PMOutput, after: PMOutput, *names):
    """Every record not named keeps exactly the same fields (types, values, references)."""
    b, a = entities(before), entities(after)
    for name in b:
        if name in names or name not in a:
            continue
        assert {k: v.model_dump() for k, v in b[name].items()} == {k: v.model_dump() for k, v in a[name].items()}, name


def test_dashboard_clause_is_not_a_record(library):
    assert set(entities(library)) == {"Member", "Book", "Loan", "Fine"}
    assert [m.label for m in library.module_specs] == ["Members", "Books", "Loans", "Fines"]
    assert any(m.label == "Overdue loans" for m in library.dashboard_metrics)


def test_split_request_into_clauses():
    assert split_request("Add a phone number and membership type (student, staff) to members and remove the fines "
                         "module. Change the colour to green") == [
        "Add a phone number and membership type (student, staff) to members", "remove the fines module",
        "Change the colour to green"]


def test_add_fields_with_values_to_an_existing_record(library):
    result = apply_change_request(library, "Add a phone number and membership type (student, staff, public) to members.")
    member = entities(result.pm)["Member"]
    assert member["membership_type"].type == "enum"
    assert member["membership_type"].enum_values == ["student", "staff", "public"]
    assert list(member)[-2:] == ["owner_id", "created_at"] or list(member)[-1] == "created_at"  # system fields stay last
    assert any("already has a Phone" in n for n in result.notes)
    unchanged_except(library, result.pm, "Member")
    assert [m.label for m in result.pm.module_specs] == [m.label for m in library.module_specs]
    assert "Change request:\nAdd a phone number" in result.pm.source_prompt


def test_new_module_takes_only_the_new_records(library):
    result = apply_change_request(library, "Add a book reservations module where members can reserve books that are on loan.")
    ents = entities(result.pm)
    assert set(ents) == {"Member", "Book", "Loan", "Fine", "BookReservation"}
    assert {"book_id", "member_id"} <= set(ents["BookReservation"])
    assert [r.name for r in result.pm.user_roles] == [r.name for r in library.user_roles]  # no side effects on roles
    assert result.pm.module_specs[-1].entities == ["BookReservation"]
    assert any(w.entity == "BookReservation" for w in result.pm.workflows)
    assert {(p.role, p.entity) for p in result.pm.role_permissions} >= {("admin", "BookReservation"), ("user", "BookReservation")}
    unchanged_except(library, result.pm)
    old_metric_ids = {m.id: m.label for m in library.dashboard_metrics}
    assert {m.id: m.label for m in result.pm.dashboard_metrics if m.id in old_metric_ids} == old_metric_ids


def test_remove_a_module_cleans_every_reference(library):
    result = apply_change_request(library, "Remove the fines module.")
    pm = result.pm
    assert "Fine" not in entities(pm) and "Fine" in result.removed
    assert all("Fine" not in m.entities for m in pm.module_specs)
    assert not [p for p in pm.role_permissions if p.entity == "Fine"]
    assert not [m for m in pm.dashboard_metrics if m.entity == "Fine"]
    assert "Fines: create, view, edit and delete fines" in library.features
    assert not any(f.startswith("Fines:") for f in pm.features)
    unchanged_except(library, pm)


def test_remove_field_status_role_rename_theme(library):
    pm = apply_change_request(library, "Add a 'lost' status to loans and remove the notes field from fines. "
                                       "Rename the Books module to Catalogue. Change the primary colour to green.").pm
    loan_flow = next(w for w in pm.workflows if w.entity == "Loan")
    assert loan_flow.states[-1] == "lost" and any(t.to_state == "lost" for t in loan_flow.transitions)
    assert "notes" not in entities(pm)["Fine"]
    assert next(m for m in pm.module_specs if "Book" in m.entities).label == "Catalogue"
    assert pm.theme["primary_color"].startswith("#")

    pm = apply_change_request(library, "Add a librarian role who can manage books and loans but not members.").pm
    perms = {(p.role, p.entity): p.actions for p in pm.role_permissions if p.role == "librarian"}
    assert perms[("librarian", "Book")] == ["create", "delete", "read", "update"]
    assert perms[("librarian", "Member")] == []
    assert perms[("librarian", "Fine")] == ["read"]
    user = next(e for e in pm.database_entities if e.is_system)
    assert "librarian" in next(f for f in user.fields if f.name == "role").enum_values


def test_removing_a_missing_field_never_removes_the_record(library):
    for request in ("Remove the notes field from members.", "Remove notes from members.",
                    "Delete the overdue loans card.", "Remove overdue loans."):
        result = apply_change_request(library, request)
        assert set(entities(result.pm)) == set(entities(library)), request
    result = apply_change_request(library, "Remove the notes field from members.")
    assert any("Member has no field matching 'notes'" in u for u in result.unresolved)
    assert diff_specs(library, result.pm) == []


def test_unsupported_and_vague_requests_are_reported(library):
    result = apply_change_request(library, "Add online payments for fines. Make it look nicer.")
    assert result.applied == []
    assert any("Online payment" in u for u in result.unresolved)
    assert any("too general" in u for u in result.unresolved)
    assert diff_specs(library, result.pm) == []


def test_preservation_guard_restores_what_was_not_removed(library):
    broken = PMOutput.model_validate(library.model_dump())
    broken.database_entities = [e for e in broken.database_entities if e.name != "Book"]
    member = next(e for e in broken.database_entities if e.name == "Member")
    member.fields = [f for f in member.fields if f.name != "email"]
    broken.user_roles = [r for r in broken.user_roles if r.name != "user"]
    restored = preserve_existing(library, broken, removed=set())
    assert {"Book records", "field Member.email", "role 'user'"} <= set(restored)
    assert set(entities(broken)) == set(entities(library))
    # explicit removals are respected
    again = PMOutput.model_validate(library.model_dump())
    again.database_entities = [e for e in again.database_entities if e.name != "Fine"]
    assert "Fine records" not in preserve_existing(library, again, removed={"Fine"})


def test_change_plan_selects_only_the_affected_agents(library):
    colour = apply_change_request(library, "Change the primary colour to green.")
    plan = build_change_plan(library, colour.pm, "Change the primary colour to green.", colour.applied, [], [], "run_1", 1)
    actions = {a.agent: a.action for a in plan.agents}
    assert actions == {"pm": "plan", "ui": "update", "backend": "reuse", "db": "reuse", "auth": "reuse",
                       "qa": "validate", "deploy": "package"}
    assert plan.agents_to_run() == ["pm", "ui", "qa", "deploy"]

    field = apply_change_request(library, "Add a membership type (student, staff) to members.")
    plan = build_change_plan(library, field.pm, "x", field.applied, [], [])
    assert {a.agent: a.action for a in plan.agents}["auth"] == "reuse"
    assert {a.agent: a.action for a in plan.agents}["db"] == "update"
    assert plan.preserved["records"] == 4 and plan.changes[0].target == "Member.membership_type"


def test_pm_agent_refine_mode(library, tmp_path):
    agent = PMAgent(user_prompt="Remove the fines module.", previous_requirements=library.model_dump(),
                    refine={"base_run_id": "run_1", "base_version": 1}, output_filepath=str(tmp_path / "req.json"))
    out = agent.run()
    assert out.change_plan.base_version == 1 and "Fine" not in entities(out)
    assert json.loads((tmp_path / "req.json").read_text())["change_plan"]["summary"]

    with pytest.raises(RefinementNoChange, match="too general"):
        PMAgent(user_prompt="Make it look nicer please.", previous_requirements=library.model_dump(),
                refine={"base_version": 1}, output_filepath=str(tmp_path / "r2.json")).run()
    with pytest.raises(PromptValidationError):
        PMAgent(user_prompt="hi", previous_requirements=library.model_dump(), refine={},
                output_filepath=str(tmp_path / "r3.json")).run()


def test_pm_agent_refine_with_llm_operations(library, tmp_path, fake_llm):
    fake_llm(json.dumps({"operations": [
        {"op": "add_fields", "entity": "Member", "fields": [{"name": "membership_type", "type": "enum",
                                                             "enum_values": ["Student", "Staff"]}]},
        {"op": "remove_entities", "entities": ["Fine"]},
        {"op": "remove_entities", "entities": ["NotARecord"]},
    ], "unresolved": []}))
    out = PMAgent(user_prompt="Members get a membership type; drop fines.", previous_requirements=library.model_dump(),
                  refine={"base_version": 2}, output_filepath=str(tmp_path / "req.json")).run()
    assert out.generation_mode == "llm"
    assert entities(out)["Member"]["membership_type"].enum_values == ["student", "staff"]
    assert "Fine" not in entities(out) and {"Member", "Book", "Loan"} <= set(entities(out))


def test_pm_agent_refine_falls_back_when_the_llm_fails(library, tmp_path, fake_llm):
    fake_llm("not json at all")
    out = PMAgent(user_prompt="Change the primary colour to green.", previous_requirements=library.model_dump(),
                  refine={"base_version": 1}, output_filepath=str(tmp_path / "req.json")).run()
    assert out.generation_mode == "deterministic_fallback" and out.theme["primary_color"].startswith("#")
