"""Generalization of the prompt-driven specification and of the generated applications.

Covers the six required domains (hospital, fleet, learning, e-commerce, project management and an
unfamiliar domain), the user's real MediCare prompts, requirement-based QA, isolation between
concurrent generations and regressions of the original failure (generic Products/Categories/Rooms
apps for every prompt).
"""

import json
import re
import threading
from pathlib import Path

import pytest

from backend.agents.pm_analysis import analyze_prompt
from backend.agents.requirement_coverage import check_requirement_coverage
from backend.codegen import auth_writer, backend_writer, db_writer, frontend_writer, qa_writer
from backend.codegen.blueprint import build_blueprint
from backend.codegen.project_files import GeneratedProject
from backend.services.pipeline import AgentStatus, ForgePipeline

DATA = Path(__file__).parent / "prompts"

DOMAINS = {
    "hospital": ("Build a hospital management system with patients, doctors, appointments, admissions, beds, "
                 "pharmacy, laboratory, and billing.",
                 ["Patients", "Doctors", "Appointments", "Admissions", "Beds", "Pharmacy", "Laboratory", "Billing"],
                 {"Patient", "Doctor", "Appointment", "Admission", "Bed", "Medicine", "LabTest", "Invoice"}),
    "fleet": ("Build a fleet management application with vehicles, drivers, trips, maintenance, fuel records, and "
              "vehicle assignments.",
              ["Vehicles", "Drivers", "Trips", "Maintenance", "Fuel records", "Vehicle assignments"],
              {"Vehicle", "Driver", "Trip", "Maintenance", "FuelRecord", "VehicleAssignment"}),
    "lms": ("Build a learning management system with students, teachers, courses, lessons, attendance, assignments, "
            "and examinations.",
            ["Students", "Teachers", "Courses", "Lessons", "Attendance", "Assignments", "Examinations"],
            {"Student", "Teacher", "Course", "Lesson", "Attendance", "Assignment", "Examination"}),
    "ecommerce": ("Build an e-commerce platform with products, shopping cart, customers, orders, payments, inventory, "
                  "and delivery tracking.",
                  ["Products", "Shopping cart", "Customers", "Orders", "Payments", "Inventory", "Delivery tracking"],
                  {"Product", "CartItem", "Customer", "Order", "Payment", "InventoryItem", "Delivery"}),
    "projects": ("Build a project management tool with projects, tasks, teams, milestones, deadlines, comments, and "
                 "progress tracking.",
                 ["Projects", "Tasks", "Teams", "Milestones", "Comments"],
                 {"Project", "Task", "Team", "Milestone", "Comment"}),
    "beekeeping": ("Build an apiary management app for beekeepers to manage hives, queens, inspections, honey "
                   "harvests, and swarm reports.",
                   ["Hives", "Queens", "Inspections", "Honey harvests", "Swarm reports"],
                   {"Hive", "Queen", "Inspection", "HoneyHarvest", "SwarmReport"}),
}
GENERIC_TEMPLATE = {"Product", "Category", "Contact", "Booking", "Employee", "Room"}


def app_entities(pm):
    return {e.name for e in pm.database_entities if not e.is_system}


def field_map(pm, entity):
    return {f.name: f for e in pm.database_entities if e.name == entity for f in e.fields}


# ---------------------------------------------------------------------------------------------
# specification per domain
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("domain", list(DOMAINS))
def test_each_domain_gets_its_own_modules_and_records(domain):
    prompt, labels, entities = DOMAINS[domain]
    pm = analyze_prompt(prompt)
    assert [m.label for m in pm.module_specs if m.kind == "entities"] == labels
    assert app_entities(pm) == entities
    if domain != "ecommerce":
        assert not (app_entities(pm) & GENERIC_TEMPLATE), "generic template records leaked into the specification"
    assert pm.purpose and pm.purpose != pm.source_prompt
    assert pm.dashboard_metrics and all(m.kind != "ask" for m in pm.dashboard_metrics)


def test_six_domains_produce_six_different_applications():
    specs = {d: analyze_prompt(p) for d, (p, _labels, _e) in DOMAINS.items()}
    names = {pm.project_name for pm in specs.values()}
    assert len(names) == len(DOMAINS)
    entity_sets = [frozenset(app_entities(pm)) for pm in specs.values()]
    assert len(set(entity_sets)) == len(DOMAINS)
    for a in range(len(entity_sets)):
        for b in range(a + 1, len(entity_sets)):
            assert len(entity_sets[a] & entity_sets[b]) <= 1  # domains share at most one generic record type


def test_hospital_specification_has_domain_workflows_and_rules():
    pm = analyze_prompt(DOMAINS["hospital"][0])
    admission = field_map(pm, "Admission")
    assert admission["bed_id"].references == "Bed" and admission["patient_id"].references == "Patient"
    assert admission["status"].enum_values == ["admitted", "discharged"]
    workflows = {w.entity: [t.action for t in w.transitions] for w in pm.workflows}
    assert workflows["Admission"] == ["discharge"]
    rules = {(r.kind, r.entity) for r in pm.business_rules}
    assert ("allocation", "Admission") in rules and ("computed", "Invoice") in rules
    assert ("date_order", "Admission") in rules


def test_fleet_specification_allocates_vehicles_and_drivers_only_for_lifecycle_records():
    pm = analyze_prompt(DOMAINS["fleet"][0])
    alloc = {(r.entity, r.fields[0]) for r in pm.business_rules if r.kind == "allocation"}
    assert ("Trip", "vehicle_id") in alloc and ("Trip", "driver_id") in alloc
    assert not any(entity == "FuelRecord" for entity, _ in alloc)  # fuel records have no lifecycle
    maintenance = next(r for r in pm.business_rules if r.kind == "allocation" and r.entity == "Maintenance")
    assert maintenance.params["occupied"] == "maintenance"


def test_project_management_maps_attribute_requests_to_fields_and_metrics():
    pm = analyze_prompt(DOMAINS["projects"][0])
    assert "progress" in field_map(pm, "Project")
    kinds = {(m.kind, m.entity) for m in pm.dashboard_metrics}
    assert ("average", "Project") in kinds and ("upcoming", "Task") in kinds
    assert any("deadlines" in a for a in pm.ambiguities)


def test_unfamiliar_domain_is_modelled_from_the_prompt():
    pm = analyze_prompt("Build a coral reef restoration tracker for marine biologists with reef sites, coral "
                        "fragments, nursery tables, outplanting events and water quality readings.")
    ents = app_entities(pm)
    assert {"ReefSite", "CoralFragment", "NurseryTable", "OutplantingEvent", "WaterQualityReading"} <= ents
    assert not (ents & GENERIC_TEMPLATE)
    assert "marine_biologist" in {r.name for r in pm.user_roles}
    assert any("not in FORGE AI's vocabulary" in a for a in pm.ambiguities)  # reported, not invented silently


# ---------------------------------------------------------------------------------------------
# the user's real prompts (original failure)
# ---------------------------------------------------------------------------------------------

def test_medicare_prompt_specification():
    pm = analyze_prompt((DATA / "medicare_prompt.txt").read_text(encoding="utf-8"))
    assert pm.project_name == "MediCare Hospital"
    labels = [m.label for m in pm.module_specs]
    assert labels == ["Patients", "Doctors", "Appointments", "Departments", "Admissions & Beds", "Billing & Payments",
                      "Pharmacy", "Staff", "Reports"]
    ents = app_entities(pm)
    assert {"Patient", "Doctor", "Appointment", "Department", "Admission", "Bed", "Invoice", "Payment", "Medicine",
            "MedicineSale", "Staff"} == ents
    assert not ({"Product", "Category", "Contact", "Booking", "Employee"} & ents)
    assert not any(re.search(r"theme|navigation|card|form|blue|layout", e, re.I) for e in ents)  # design words
    assert {r.name for r in pm.user_roles} == {"admin", "doctor", "receptionist", "nurse", "pharmacist"}
    patient = field_map(pm, "Patient")
    assert {"name", "age", "gender", "phone", "address", "blood_group", "medical_history"} <= set(patient)
    appointment = field_map(pm, "Appointment")
    assert appointment["appointment_time"].type == "time"
    assert appointment["status"].enum_values == ["scheduled", "completed", "cancelled"]
    rules = {(r.kind, r.entity, tuple(r.fields)) for r in pm.business_rules}
    assert ("unique_together", "Appointment", ("doctor_id", "appointment_date", "appointment_time")) in rules
    assert ("low_stock", "Medicine", ("quantity",)) in rules and ("expiry", "Medicine", ("expiry_date",)) in rules
    assert ("allocation", "Admission", ("bed_id",)) in rules
    labels_m = {m.label for m in pm.dashboard_metrics}
    assert {"Available beds", "Admitted patients", "Monthly revenue", "Appointment trends"} <= labels_m
    assert [r["name"] for r in pm.seed_records["Department"]] == [
        "Cardiology", "Neurology", "Orthopedics", "Pediatrics", "Dermatology", "General Medicine"]
    assert pm.demo_data is True
    assert any("Printable" in u for u in pm.unsupported_requests)
    perms = {(p.role, p.entity): p.actions for p in pm.role_permissions}
    assert "create" in perms[("receptionist", "Patient")] and "create" not in perms[("doctor", "Patient")]
    assert "create" in perms[("pharmacist", "Medicine")]


def test_medicare_correction_prompt_specification():
    pm = analyze_prompt((DATA / "medicare_correction_prompt.txt").read_text(encoding="utf-8"))
    assert pm.project_name == "MediCare Hospital"
    ents = app_entities(pm)
    assert {"Patient", "MedicalRecord", "Doctor", "Appointment", "Department", "Room", "Bed", "Admission", "Medicine",
            "LabTest", "Invoice", "Payment", "Staff", "Prescription"} == ents
    assert "Product" not in ents and "Category" not in ents  # "Replace Products and Categories with ..."
    assert pm.theme == {"primary_color": "#0d9488", "sidebar_color": "#1e3a8a"}  # teal accent, navy sidebar
    metrics = {m.label: (m.kind, m.entity, m.value) for m in pm.dashboard_metrics}
    assert metrics["Today's appointments"][:2] == ("count_today", "Appointment")
    assert metrics["Occupied beds"] == ("count_where", "Bed", "occupied")
    assert metrics["Pending bills"][1] == "Invoice"
    assert field_map(pm, "Bed")["status"].enum_values == ["available", "occupied", "reserved", "maintenance"]


def test_shopsphere_prompt_reports_what_cannot_be_generated():
    pm = analyze_prompt((DATA / "shopsphere_prompt.txt").read_text(encoding="utf-8"))
    assert pm.project_name == "ShopSphere"
    assert {"Category", "Product", "CartItem", "Order"} == app_entities(pm)
    assert {"name", "image_url", "price", "rating", "description"} <= set(field_map(pm, "Product"))
    assert any("storefront" in u.lower() for u in pm.unsupported_requests)


def test_negation_removes_rejected_records():
    pm = analyze_prompt("Build a clinic app with patients, visits and invoices. Do not include products or categories.")
    assert {"Patient", "Visit", "Invoice"} <= app_entities(pm)
    assert not ({"Product", "Category"} & app_entities(pm))


# ---------------------------------------------------------------------------------------------
# generated code and requirement-based QA
# ---------------------------------------------------------------------------------------------

def generate(prompt: str, root: Path):
    pm = analyze_prompt(prompt)
    bp = build_blueprint(pm)
    project = GeneratedProject(root)
    ui = frontend_writer.build_ui_spec(bp)
    api = backend_writer.build_api_spec(bp)
    frontend_writer.write_frontend_files(bp, project, ui)
    backend_writer.write_backend_files(bp, project)
    db_writer.write_db_files(bp, project)
    auth_writer.write_auth_files(bp, project, api)
    qa_writer.write_test_files(bp, project)
    return pm, bp, project


def nav_labels(root: Path):
    text = (root / "frontend" / "src" / "config" / "app.js").read_text(encoding="utf-8")
    nav = json.loads(re.search(r"export const NAV_ITEMS = (.*?);\s*$", text, re.S).group(1))
    return [n["label"] for n in nav]


def test_generated_navigation_follows_the_prompt(tmp_path):
    for domain, (prompt, labels, _e) in DOMAINS.items():
        _pm, _bp, project = generate(prompt, tmp_path / domain)
        nav = nav_labels(project.root)
        assert nav[0] == "Dashboard" and nav[-1] == "Admin"
        assert [label for label in nav[1:-1] if label != "Reports"] == labels


def test_dashboard_never_shows_the_raw_prompt(tmp_path):
    prompt = (DATA / "medicare_prompt.txt").read_text(encoding="utf-8")
    _pm, _bp, project = generate(prompt, tmp_path / "medicare")
    app_js = (project.root / "frontend" / "src" / "config" / "app.js").read_text(encoding="utf-8")
    assert prompt[:80] not in app_js
    assert "APP_DESCRIPTION" not in (project.root / "frontend" / "src" / "pages" / "DashboardPage.jsx").read_text(encoding="utf-8")


def test_requirement_coverage_passes_for_generated_app_and_detects_gaps(tmp_path):
    pm, bp, project = generate(DOMAINS["hospital"][0], tmp_path / "hospital")
    report = check_requirement_coverage(pm, project.root)
    assert report["missing"] == 0, [i for i in report["items"] if i["status"] == "missing"]
    assert report["covered"] > 50
    # inject the original failure: a generic module in navigation and a missing workflow step
    app_js = project.root / "frontend" / "src" / "config" / "app.js"
    app_js.write_text(app_js.read_text(encoding="utf-8").replace('"label": "Beds"', '"label": "Products"'),
                      encoding="utf-8")
    router = project.root / "backend" / "app" / "routers" / "admissions.py"
    router.write_text(router.read_text(encoding="utf-8").replace('"discharge":', '"leave":'), encoding="utf-8")
    broken = check_requirement_coverage(pm, project.root)
    missing = {i["requirement"] for i in broken["items"] if i["status"] == "missing"}
    assert "No unrequested module ('Products')" in missing
    assert "Module 'Beds'" in missing
    assert any(m.startswith("Admission: Discharge") for m in missing)
    agents = {t["agent"] for t in broken["correction_tasks"]}
    assert {"UIAgent", "BackendAgent"} <= agents


# ---------------------------------------------------------------------------------------------
# full seven-agent runs (QA executes each generated app's own test-suite)
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("domain", list(DOMAINS))
def test_full_pipeline_generates_a_tested_app_per_domain(domain, tmp_path):
    prompt, labels, entities = DOMAINS[domain]
    pipeline = ForgePipeline(user_prompt=prompt, output_dir=str(tmp_path / domain), qa_frontend_build=False,
                             deploy_health_check=True)
    state = pipeline.run_pipeline()
    assert state.execution_status == AgentStatus.COMPLETED, state.error_reports
    qa = state.agent_outputs["qa"]
    assert qa["status"] == "passed" and qa["tests_failed"] == 0 and qa["tests_run"] >= 40
    checks = {c["name"]: c["status"] for c in qa["checks"]}
    assert checks["Requirement coverage (prompt specification vs generated app)"] == "passed"
    assert not [i for i in qa["requirement_coverage"] if i["status"] == "missing"]
    suites = {t["suite"] for t in qa["test_results"]}
    assert {"test_permissions", "test_dashboard_metrics"} <= suites
    deploy = state.agent_outputs["deploy"]
    assert deploy["status"] == "success"
    assert all(h["status"] == "healthy" for h in deploy["health_checks"])
    assert any(h["endpoint"].startswith("GET /api (application identity)") for h in deploy["health_checks"])
    assert [label for label in nav_labels(Path(state.app_dir))[1:-1] if label != "Reports"] == labels


def test_concurrent_generations_are_isolated(tmp_path):
    prompts = {"fleet": DOMAINS["fleet"][0], "beekeeping": DOMAINS["beekeeping"][0]}
    states = {}

    def run(name, prompt):
        pipeline = ForgePipeline(user_prompt=prompt, output_dir=str(tmp_path / name), qa_frontend_build=False,
                                 deploy_health_check=False)
        states[name] = pipeline.run_pipeline()

    threads = [threading.Thread(target=run, args=item) for item in prompts.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=600)
    for name in prompts:
        assert states[name].execution_status == AgentStatus.COMPLETED, states[name].error_reports
    fleet_app, bee_app = Path(states["fleet"].app_dir), Path(states["beekeeping"].app_dir)
    assert fleet_app != bee_app
    fleet_models = (fleet_app / "backend" / "app" / "models.py").read_text(encoding="utf-8")
    bee_models = (bee_app / "backend" / "app" / "models.py").read_text(encoding="utf-8")
    assert "class Vehicle(Base)" in fleet_models and "class Hive(Base)" not in fleet_models
    assert "class Hive(Base)" in bee_models and "class Vehicle(Base)" not in bee_models
    assert states["fleet"].agent_outputs["pm"]["project_name"] != states["beekeeping"].agent_outputs["pm"]["project_name"]
