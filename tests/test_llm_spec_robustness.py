"""Specifications an LLM writes, which the rule-based extractor never produced.

Found with Groq: a record called 'Owner' made its links 'owner_id' (the column that records which user owns a row),
and a unique-together rule made only of numbers ("freezer, shelf, position") broke the generated tests.
"""

import json

from backend.agents.pm_analysis import analyze_prompt, normalize_requirements
from backend.codegen.blueprint import build_blueprint
from backend.codegen.qa_spec_tests import render_rule_tests
from backend.codegen.qa_writer import render_factories
from backend.schemas.pm_schema import PMOutput
from backend.services.pipeline import AgentStatus, ForgePipeline

LLM_SPEC = {
    "project_name": "Paws Clinic",
    "description": "A vet clinic with owners, pets and a sample freezer.",
    "user_roles": [{"name": "receptionist", "description": "Front desk"}],
    "database_entities": [
        {"name": "Owner", "access": "shared", "fields": [
            {"name": "full_name", "type": "string", "nullable": False}, {"name": "phone", "type": "string"}]},
        {"name": "Pet", "access": "owner", "fields": [
            {"name": "name", "type": "string", "nullable": False},
            {"name": "owner", "type": "reference", "references": "Owner", "nullable": False}]},
        {"name": "FreezerSlot", "access": "admin_managed", "fields": [
            {"name": "freezer_number", "type": "integer", "nullable": False, "min_value": 1, "max_value": 20},
            {"name": "shelf", "type": "integer", "nullable": False},
            {"name": "position", "type": "integer", "nullable": False}]},
    ],
    "module_specs": [
        {"key": "owners", "name": "Owners", "label": "Owners", "entities": ["Owner"]},
        {"key": "pets", "name": "Pets", "label": "Pets", "entities": ["Pet"]},
        {"key": "freezer", "name": "Freezer", "label": "Freezer", "entities": ["FreezerSlot"]},
    ],
    "business_rules": [
        {"id": "r1", "kind": "unique_together", "entity": "FreezerSlot",
         "fields": ["freezer_number", "shelf", "position"], "description": "Each freezer slot is unique"},
        {"id": "r2", "kind": "unique_together", "entity": "Pet", "fields": ["owner_id", "name"],
         "description": "An owner's pets have different names"},
    ],
}


def entity(pm, name):
    return next(e for e in pm.database_entities if e.name == name)


def refs(pm, name):
    return {f.name: f.references for f in entity(pm, name).fields if f.type == "reference"}


def test_linked_owner_records_are_renamed_away_from_the_ownership_column():
    pm = normalize_requirements(PMOutput.model_validate(LLM_SPEC))
    names = [e.name for e in pm.database_entities]
    assert "Owner" not in names and "PetOwner" in names
    assert refs(pm, "Pet") == {"pet_owner_id": "PetOwner", "owner_id": "User"}  # link + record ownership
    assert next(m for m in pm.module_specs if m.key == "owners").label == "Owners"  # screens keep the name
    rule = next(r for r in pm.business_rules if r.entity == "Pet")
    assert rule.fields == ["pet_owner_id", "name"]
    assert any("PetOwner" in a for a in pm.ambiguities)
    again = normalize_requirements(pm)  # refinements normalise an already normalised spec
    assert [e.name for e in again.database_entities] == names and refs(again, "Pet") == refs(pm, "Pet")


def test_an_owner_nothing_links_to_keeps_its_name():
    pm = analyze_prompt("Build a vet app to manage owners, pets and appointments.")
    assert "Owner" in [e.name for e in pm.database_entities]


def test_factories_vary_numbers_of_unique_together_rules():
    bp = build_blueprint(normalize_requirements(PMOutput.model_validate(LLM_SPEC)))
    factories = render_factories(bp)
    slot = factories.split("def make_freezer_slot")[1].split("\ndef ")[0]
    assert '"freezer_number": 1 + (n % 20),' in slot  # within the field's 1..20 range
    assert '"shelf": 3,' in slot  # one varied field is enough for the rule
    rules = render_rule_tests(bp)
    duplicate = rules.split("def test_freezer_slot_duplicate_freezer_number_shelf_position_is_rejected")[1]
    assert "freezer_number=5, shelf=5, position=5" in duplicate.split("\n\n")[0] and "QA same value" not in duplicate


def test_llm_spec_with_owner_and_numeric_rule_builds_and_passes_qa(fake_llm, tmp_path):
    styling = {"primary_color": "#0f766e", "tagline": "Care for every pet", "design_system_notes": "Calm teal."}
    fake_llm(json.dumps(LLM_SPEC), json.dumps(styling))
    state = ForgePipeline(user_prompt="A vet clinic with owners, pets and a sample freezer",
                          output_dir=str(tmp_path / "paws"), qa_frontend_build=False, deploy_health_check=False
                          ).run_pipeline()
    assert state.agent_modes["pm"] == "llm"
    assert state.execution_status == AgentStatus.COMPLETED, state.error_reports
    qa = state.agent_outputs["qa"]
    assert qa["status"] == "passed" and qa["tests_failed"] == 0
