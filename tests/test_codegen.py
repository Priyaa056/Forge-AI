"""Code generation layer: naming, blueprint, writers, manifests and cross-agent contract checks."""

import ast
import json

import pytest

from backend.agents.pm_analysis import analyze_prompt
from backend.codegen import auth_writer, backend_writer, db_writer, frontend_writer, qa_writer
from backend.codegen.blueprint import build_blueprint
from backend.codegen.naming import pluralize, safe_identifier, singularize, to_pascal, to_snake
from backend.codegen.project_files import GeneratedProject, file_tree, verify_manifest

from .conftest import SHOP_PROMPT, TASK_PROMPT


def test_naming_helpers():
    assert pluralize("category") == "categories"
    assert pluralize("order_item") == "order_items"
    assert pluralize("status") == "statuses"
    assert singularize("categories") == "category"
    assert to_snake("OrderItem") == "order_item"
    assert to_pascal("order item") == "OrderItem"
    assert safe_identifier("class") == "class_value"
    assert safe_identifier("metadata") == "metadata_value"


@pytest.fixture
def shop_project(tmp_path):
    bp = build_blueprint(analyze_prompt(SHOP_PROMPT))
    project = GeneratedProject(tmp_path / "app")
    ui = frontend_writer.build_ui_spec(bp)
    api = backend_writer.build_api_spec(bp)
    frontend_writer.write_frontend_files(bp, project, ui)
    backend_writer.write_backend_files(bp, project)
    db_writer.write_db_files(bp, project)
    auth_writer.write_auth_files(bp, project, api)
    qa_writer.write_test_files(bp, project)
    project.save_manifest()
    return bp, project, ui, api


def test_all_generated_python_is_valid(shop_project):
    _bp, project, _ui, _api = shop_project
    py_files = [p for p in (project.root / "backend").rglob("*.py")]
    assert len(py_files) > 15
    for path in py_files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_generated_structure_and_ownership(shop_project):
    bp, project, _ui, _api = shop_project
    paths = {f["path"] for f in file_tree(project.root)}
    for expected in ["backend/app/main.py", "backend/app/models.py", "backend/app/security.py",
                     "backend/app/routers/products.py", "backend/app/routers/order_items.py",
                     "backend/migrations/001_initial_schema.sql", "frontend/src/App.jsx",
                     "frontend/src/pages/CartItemsPage.jsx", "frontend/src/auth/AuthContext.jsx",
                     "backend/tests/test_orders.py"]:
        assert expected in paths, expected
    owners = {p: m["agent"] for p, m in project.manifest.items()}
    assert owners["backend/app/models.py"] == "db"
    assert owners["backend/app/security.py"] == "auth"
    assert owners["backend/app/routers/products.py"] == "backend"
    assert owners["frontend/src/App.jsx"] == "ui"
    assert owners["backend/tests/conftest.py"] == "qa"
    assert verify_manifest(project.root) == []


def test_manifest_detects_tampering(shop_project):
    _bp, project, _ui, _api = shop_project
    (project.root / "backend" / "app" / "models.py").write_text("# tampered\n", encoding="utf-8")
    (project.root / "frontend" / "src" / "App.jsx").unlink()
    problems = verify_manifest(project.root)
    assert "modified: backend/app/models.py" in problems
    assert "missing: frontend/src/App.jsx" in problems


def test_project_writer_refuses_paths_outside_project(tmp_path):
    project = GeneratedProject(tmp_path / "app")
    with pytest.raises(ValueError):
        project.write("../escape.txt", "x", "ui")


def test_rbac_matrix_follows_access_policies(shop_project):
    bp, _project, _ui, api = shop_project
    perms = auth_writer.role_permissions(bp, api)
    assert perms["admin"] == ["*"]
    assert "products:read" in perms["user"] and "products:create" not in perms["user"]
    assert {"orders:create", "orders:delete", "cart_items:update"} <= set(perms["user"])


def test_owner_scoped_unique_fields_are_unique_per_owner():
    bp = build_blueprint(analyze_prompt(TASK_PROMPT))
    models = db_writer.render_models(bp)
    assert 'UniqueConstraint("owner_id", "name", name="uq_categories_owner_name")' in models
    up, down = db_writer.render_migration_sql(bp)
    assert "CONSTRAINT uq_categories_owner_name UNIQUE (owner_id, name)" in up
    assert "REFERENCES categories(id) ON DELETE SET NULL" in up
    assert "DROP TABLE IF EXISTS users CASCADE;" in down


def test_ui_contract_check_detects_missing_endpoints(shop_project):
    _bp, _project, ui, api = shop_project
    coverage = backend_writer.check_ui_contract(api, ui["api_requirements"])
    assert coverage["missing"] == []
    assert any(item.startswith("POST /api/auth/login") for item in coverage["delegated_to_auth"])
    broken = backend_writer.check_ui_contract(api, ui["api_requirements"] + [{"endpoint": "/api/reports", "method": "GET"}])
    assert broken["missing"] == ["GET /api/reports"]


def test_entity_ui_config_is_valid_json(shop_project):
    _bp, project, _ui, _api = shop_project
    text = (project.root / "frontend" / "src" / "config" / "entities.js").read_text(encoding="utf-8")
    config = json.loads(text.split("=", 1)[1].strip().rstrip(";"))
    assert config["OrderItem"]["endpoint"] == "/api/order-items"
    product_ref = next(f for f in config["CartItem"]["fields"] if f["name"] == "product_id")
    assert product_ref["reference"]["endpoint"] == "/api/products"
