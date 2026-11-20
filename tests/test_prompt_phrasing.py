"""Prompts phrased as actions, colon lists and sentences that name people.

Found with a held-out accuracy check: "candidates apply" became a record called 'CandidatesApply', a list after
"Car rental app:" was not read at all, and "Receptionists book appointments" created no receptionist role.
"""

import pytest

from backend.agents.spec_extraction import _clause, extract_spec
from backend.services.pipeline import AgentStatus, ForgePipeline


def records(pm):
    return [e.name for e in pm.database_entities if not e.is_system]


def refs(pm, name):
    entity = next(e for e in pm.database_entities if e.name == name)
    return {f.name for f in entity.fields if f.name.endswith("_id")}


def roles(pm):
    return {r.name for r in pm.user_roles}


def test_clauses_name_records_not_clause_text():
    pm = extract_spec("Build an applicant tracking system where recruiters post job openings, candidates apply, and "
                      "interviews are scheduled with feedback.")
    assert records(pm) == ["JobOpening", "Candidate", "Application", "Interview"]
    assert refs(pm, "Application") == {"candidate_id", "job_opening_id"}
    assert refs(pm, "Interview") == {"application_id", "candidate_id"}
    assert "feedback" in {f.name for e in pm.database_entities if e.name == "Interview" for f in e.fields}
    assert roles(pm) >= {"recruiter", "candidate"}


def test_passive_clauses_and_subject_verb_object():
    pm = extract_spec("Research lab sample tracker: researchers register samples, experiments use samples, results are "
                      "recorded, and freezer storage locations are tracked.")
    assert records(pm) == ["Sample", "Experiment", "Result", "FreezerStorageLocation"]
    assert refs(pm, "Experiment") == {"sample_id"}
    assert "researcher" in roles(pm)


def test_list_after_app_colon():
    pm = extract_spec("Car rental app: customers, cars, rental bookings, payments and damage reports.")
    assert records(pm) == ["Customer", "Car", "RentalBooking", "Payment", "DamageReport"]


def test_people_acting_in_sentences_become_roles_without_duplicate_records():
    pm = extract_spec("Build a veterinary clinic app to manage pet owners, pets, vet appointments, vaccinations and "
                      "invoices. Receptionists book appointments and vets record vaccinations.")
    # "appointments" is the vet appointments already listed; "vets record vaccinations" is not a record
    assert records(pm) == ["PetOwner", "Pet", "VetAppointment", "Vaccination", "Invoice"]
    assert roles(pm) >= {"receptionist", "vet"}


def test_where_clauses_with_any_verb():
    pm = extract_spec("Build a school app where students enroll in courses, teachers grade assignments and attendance "
                      "is tracked.")
    assert records(pm) == ["Student", "Course", "Enrollment", "Assignment", "Attendance"]
    assert refs(pm, "Enrollment") == {"student_id", "course_id"}
    assert roles(pm) >= {"student", "teacher"}


def test_roles_from_sentences_and_passive_agents():
    pm = extract_spec("Inventory app: products, purchase orders, sales orders and suppliers. Managers approve purchase "
                      "orders.")
    assert records(pm) == ["Product", "PurchaseOrder", "SalesOrder", "Supplier"]
    assert "manager" in roles(pm)
    pm = extract_spec("Build an HR app with employees, departments, leave requests and payroll. Leave requests are "
                      "approved by managers.")
    assert "manager" in roles(pm) and "LeaveRequest" in records(pm)


def test_declared_roles_are_the_complete_list():
    pm = extract_spec("App: Salon booking\nFeatures:\n- Clients\n- Stylists\n- Services with price and duration\n"
                      "- Appointments\n- Product sales\nRoles: admin, stylist, receptionist\n\n"
                      "Clients book appointments.")
    assert roles(pm) == {"admin", "stylist", "receptionist"}


@pytest.mark.parametrize("phrase", ["purchase orders", "sales report", "sales order", "assets register",
                                    "damage reports", "job openings", "employees leave requests"])
def test_noun_phrases_are_not_clauses(phrase):
    assert _clause(phrase) is None


@pytest.mark.parametrize("phrase, subject, verb, obj, passive", [
    ("candidates apply", ["candidates"], "apply", "", False),
    ("experiments use samples", ["experiments"], "use", "samples", False),
    ("results are recorded", ["results"], "recorded", "", True),
    ("certified technicians sign off tasks", ["certified", "technicians"], "sign", "tasks", False),
    ("front desk staff check guests in", ["front", "desk", "staff"], "check", "guests in", False),
])
def test_clause_reader(phrase, subject, verb, obj, passive):
    assert _clause(phrase) == (subject, verb, obj, passive)


def test_action_prompt_builds_and_passes_qa(tmp_path):
    pipeline = ForgePipeline(user_prompt="Build an applicant tracking system where recruiters post job openings, "
                                         "candidates apply, and interviews are scheduled with feedback.",
                             output_dir=str(tmp_path / "ats"), qa_frontend_build=False, deploy_health_check=False)
    state = pipeline.run_pipeline()
    assert state.execution_status == AgentStatus.COMPLETED, state.error_reports
    qa = state.agent_outputs["qa"]
    assert qa["status"] == "passed" and qa["tests_failed"] == 0 and qa["tests_run"] > 20
