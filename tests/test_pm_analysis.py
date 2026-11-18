"""PM agent requirement analysis: prompt validation, domain/entity extraction and normalization."""

import pytest

from backend.agents.pm_agent import PMAgent, generate_pm_output
from backend.agents.pm_analysis import PromptValidationError, analyze_prompt, normalize_requirements
from backend.schemas.pm_schema import DatabaseEntity, EntityField, PMOutput

from .conftest import SHOP_PROMPT, TASK_PROMPT


def entities(pm):
    return {e.name: e for e in pm.database_entities}


@pytest.mark.parametrize("prompt", ["", "   ", "app", "make app now", "asdf qwrt zxcv plkj mnbv", "I want something nice for me please"])
def test_vague_or_invalid_prompts_are_rejected(prompt):
    with pytest.raises(PromptValidationError):
        analyze_prompt(prompt)


def test_task_prompt_produces_prompt_specific_requirements():
    pm = analyze_prompt(TASK_PROMPT)
    ents = entities(pm)
    assert pm.app_type == "task_management"
    assert {"User", "Task", "Category"} <= set(ents)
    task_fields = {f.name: f for f in ents["Task"].fields}
    assert task_fields["status"].type == "enum" and task_fields["status"].enum_values
    assert task_fields["category_id"].references == "Category"
    assert task_fields["owner_id"].references == "User" and task_fields["owner_id"].read_only
    assert ents["Task"].access == "owner"
    assert {r.name for r in pm.user_roles} >= {"admin", "user"}
    assert pm.has_admin_dashboard
    assert pm.functional_requirements and pm.non_functional_requirements and pm.development_plan
    assert pm.source_prompt == TASK_PROMPT


def test_ecommerce_prompt_is_not_a_task_app():
    pm = analyze_prompt(SHOP_PROMPT)
    ents = entities(pm)
    assert pm.app_type == "ecommerce"
    assert {"Product", "CartItem", "Order", "OrderItem"} <= set(ents)
    assert "Task" not in ents
    assert ents["Product"].access == "admin_managed"
    refs = {f.name: f.references for f in ents["OrderItem"].fields if f.references}
    assert refs["order_id"] == "Order" and refs["product_id"] == "Product"


def test_different_prompts_give_different_requirements():
    a, b = analyze_prompt(TASK_PROMPT), analyze_prompt(SHOP_PROMPT)
    assert a.project_name != b.project_name
    assert set(entities(a)) != set(entities(b))


def test_generic_nouns_become_entities():
    pm = analyze_prompt("Create an app to track my houseplants and their watering schedule")
    assert "Houseplant" in entities(pm)


def test_named_project_is_respected():
    pm = analyze_prompt("Build a blog called DevNotes with posts, comments and tags")
    assert pm.project_name == "DevNotes"
    refs = {f.references for f in entities(pm)["Comment"].fields if f.references}
    assert "Post" in refs


def test_entities_are_ordered_by_dependency():
    pm = analyze_prompt(SHOP_PROMPT)
    order = [e.name for e in pm.database_entities]
    assert order[0] == "User"
    assert order.index("Product") < order.index("OrderItem")
    assert order.index("Order") < order.index("OrderItem")


def test_normalization_repairs_messy_llm_style_output():
    raw = PMOutput(
        project_name="Gym",
        description="Gym app",
        database_entities=[
            DatabaseEntity(name="members", access="weird", fields=[
                EntityField(name="Full Name", type="VARCHAR(100)", nullable=False),
                EntityField(name="id", type="int"),
                EntityField(name="metadata", type="text"),
                EntityField(name="plan", type="enum", enum_values=["Basic Plan", "Gold"]),
                EntityField(name="trainer", type="reference", references="Trainers"),
            ]),
            DatabaseEntity(name="Trainer", fields=[EntityField(name="name", type="str")]),
            DatabaseEntity(name="User", fields=[EntityField(name="email", type="string")]),
        ],
    )
    pm = normalize_requirements(raw)
    ents = entities(pm)
    assert set(ents) == {"User", "Member", "Trainer"}
    assert ents["User"].is_system
    member = {f.name: f for f in ents["Member"].fields}
    assert member["full_name"].type == "string"
    assert "metadata" not in member and "metadata_value" in member  # reserved by SQLAlchemy
    assert member["plan"].enum_values == ["basic_plan", "gold"]
    assert member["trainer_id"].references == "Trainer"
    assert ents["Member"].access == "owner" and "owner_id" in member
    assert list(member)[0] == "id"


def test_normalization_rejects_requirements_without_entities():
    with pytest.raises(PromptValidationError):
        normalize_requirements(PMOutput(project_name="x", description="y", database_entities=[]))


def test_pm_agent_records_deterministic_mode_and_writes_requirements_doc(tmp_path):
    from backend.codegen.project_files import GeneratedProject

    project = GeneratedProject(tmp_path / "app")
    agent = PMAgent(user_prompt=TASK_PROMPT, output_filepath=str(tmp_path / "requirements.json"), project=project)
    out = agent.run()
    assert out.generation_mode == "deterministic"
    assert (tmp_path / "requirements.json").is_file()
    assert "docs/REQUIREMENTS.md" in agent.generated_files
    assert "Task" in (tmp_path / "app" / "docs" / "REQUIREMENTS.md").read_text(encoding="utf-8")


def test_legacy_generate_pm_output_helper_returns_json():
    import json

    data = json.loads(generate_pm_output(TASK_PROMPT))
    assert data["project_name"] and data["database_entities"]
