# FORGE AI — Generation pipeline failure: root cause and fix

Date: 2026-11-19. Scope: why every prompt produced a near-identical generic application
(Products, Categories, Rooms, Contacts, Bookings, Employees + a generic dashboard), and the
architectural fix. Results marked **verified** were executed; anything else is marked as an assumption
or limitation.

## 1. Exact root cause

The application was decided by the PM agent's deterministic analyser (`backend/agents/pm_analysis.py`,
the mode used whenever no LLM key is configured, which is this installation) and not by the prompt:

1. **Context-blind keyword knowledge base.** `analyze_prompt` scanned the prompt for keywords and
   copied fixed entity templates from `ENTITY_KB` (e.g. any mention of "inventory", "stock", "room",
   "contact", "booking", "staff" pulled in Product/Category/Room/Contact/Booking/Employee with fixed fields).
2. **Requested nouns were dropped.** A noun the KB did not know (admission, bed, medicine, laboratory
   test, prescription, hive, swarm report, fuel record…) was ignored whenever the KB had already matched
   something, so domain records disappeared while generic ones remained.
3. **Fixed domain defaults.** Detected "domains" added default entity sets and fixed project names,
   entities were capped at 12, and roles were hard-wired to `admin`/`user` (Doctor, Receptionist, Nurse,
   Pharmacist were lost).
4. **Fixed UI shell.** `frontend_writer.py` generated one navigation item per entity with generic labels
   and showed the **raw prompt** as dashboard text (`APP_DESCRIPTION`), plus a fixed dashboard of
   record counts.
5. **Self-consistent QA.** The QA agent generated tests from the same (wrong) blueprint, so the tests
   always agreed with the wrong app; nothing compared the result with the prompt, and a project was
   reported successful because its code ran and built.
6. **4,000-character prompt limit** (backend validation + prompt textarea) truncated long prompts
   such as the MediCare prompt (the stored prompt ends mid-word).

Not causes (checked): prompt delivery to the agents, run/project isolation, preview targeting and
artifact storage — every agent received the right prompt and wrote to its own run directory.

## 2. Files responsible

| File | Problem |
|---|---|
| `backend/agents/pm_analysis.py` | `ENTITY_KB`, `DOMAINS`, `RELATIONS_KB`, `ROLE_KEYWORDS`, keyword matching, 12-entity cap |
| `backend/codegen/frontend_writer.py` | fixed shell/navigation, raw prompt on the dashboard |
| `backend/codegen/backend_writer.py` | fixed dashboard statistics, access-policy-only permissions |
| `backend/codegen/qa_writer.py` / `backend/agents/qa_agent.py` | tests derived from the same blueprint; no requirement check |
| `backend/agents/spec_extraction.py` (validate) + `frontend/src/components/app/PromptForm.tsx` | 4,000-character limit |

## 3. Why different prompts produced similar applications

The KB matched common words that appear in almost every business prompt ("manage", "inventory",
"stock", "room", "staff", "booking", "contact"). The same handful of templates therefore won for
hospital, fleet, school and shop prompts, the domain nouns that made each prompt different were
discarded, and the UI/QA layers faithfully rendered and tested whatever the PM produced. Evidence from
the stored runs: `proj_5e9e603270` (MediCare) generated Category, Product, Room, Contact, Booking,
Employee… with roles admin/user, and the correction prompt in `proj_c4f2c72e44` produced
Project/Review/Product.

## 4. Architecture changes

The seven-agent architecture, artifact store, run tracking, rollback, preview and accounts are
unchanged. What changed is the contract between the agents:

```
prompt -> PM: extract_spec (prompt structure) -> normalize -> finalize_spec  ==> requirements.json (spec v2)
            |  modules, entities, fields, roles, permissions, workflows, rules, metrics, seeds,
            |  ambiguities, unsupported requests, requirement trace
            v
   Blueprint (shared view of the spec) -> UI / Backend / DB / Auth / QA / Deploy
            v
   QA: generated tests (incl. permissions, workflows, rules, metrics, seeds)
       + requirement coverage (spec vs generated files and live routes)
       -> correction tasks -> one targeted re-run of the responsible agents -> QA again
            v
   Deploy: live identity check (served app name), specified dashboard metrics, every module endpoint
```

New modules: `spec_extraction.py`, `spec_finalize.py`, `attribute_lexicon.py`, `requirement_coverage.py`
(agents); `spec_runtime.py`, `frontend_spec.py`, `qa_spec_tests.py` (code generation).

## 5. Agent communication changes

* `PMOutput` (requirements.json, `spec_version = 2`) now carries: `purpose`, `target_users`,
  `module_specs`, `workflows`, `business_rules`, `dashboard_metrics`, `role_permissions`,
  `ambiguities`, `unsupported_requests`, `theme`, `seed_records`, `demo_data`, `requirement_trace`.
* `Blueprint` exposes the same spec to every agent (`modules`, `workflows`, `rules`, `metrics`,
  `permissions`, `theme`, `seed_records`…), so UI navigation, API permissions, DB seeds, auth matrix,
  tests and deploy probes all come from one source.
* QA output (`qa_report.json`) adds `requirement_coverage`, `correction_tasks` and `unsupported_requests`;
  the pipeline reads `correction_tasks` and re-runs the named agents once before failing.
* Iterations: the PM applies a change request to the previous prompt's specification
  ("also add projects and replace categories with labels") instead of treating it as a new app.
* The LLM path (Gemini) was given the same spec contract and is followed by the same
  normalization/finalization.

## 6. Specification generation changes

`extract_spec` derives everything from the prompt itself: markdown headings and numbered/bulleted
module lists, "X Management with a, b, c" titles, "with A, B and C" enumerations, verb objects
("register patients with name, age…", "book appointments by selecting a patient, doctor, date and time"),
status lists ("track available, occupied and maintenance beds"), workflow titles ("Admission and
Discharge workflows"), rules ("prevent duplicate bookings for the same doctor and time slot", low stock,
expiry, "update bed availability after discharge"), roles ("Receptionist: patient registration and
appointment management" → per-entity permissions), dashboard asks ("available beds", "today's
appointments", "monthly revenue", "pending bills"), listed records ("Include Cardiology, Neurology…"),
colours ("navy sidebar", "teal accent"), negation ("replace Products and Categories with…", "do not
show…"), and design/technology sentences (ignored as data). Unknown domains are modelled from the
prompt's own nouns (e.g. reef sites, coral fragments, nursery tables). Limit raised to 20,000 characters.

## 7. Template / fallback logic changes

* `ENTITY_KB`/`DOMAINS`/default entity sets/fixed names were removed. `attribute_lexicon.py` only
  **enriches** entities the prompt asked for (typical attributes and relations, e.g. a bed has a bed
  number and ward). Every enrichment is written to `ambiguities`; it never adds a module or entity.
* Generated UI: navigation and pages come from `module_specs` in the user's terminology
  ("Pharmacy", "Billing & Payments", "Admissions & Beds"); multi-record modules get tabs; workflow
  buttons, a record view with related records, a metric-driven dashboard, an optional Reports page and
  the requested theme. The dashboard shows a one-sentence purpose, never the prompt.
* Generated backend: workflow action endpoints, business-rule enforcement (date order 422, computed
  balance, duplicate prevention 409, resource allocation/release), spec metrics endpoint, reports,
  role-permission matrix, idempotent seeding of listed records and optional fictional demo data.
* Unsupported requests (printing, uploads, payment processing, storefront design, checkout-to-order
  conversion, maps, chat, notifications…) are reported, not faked.

## 8. Generalization tests (A–F) — verified

Each prompt was run through the **full seven-agent pipeline** (`tests/test_spec_generalization.py`,
QA executed the generated test-suite, deploy started the app and probed it; frontend Vite build
disabled in the automated runs). Generated-suite sizes are from the same generator run separately.

| | Prompt | Navigation (generated) | Generated tests | Notable spec items |
|---|---|---|---|---|
| A | Hospital | Patients, Doctors, Appointments, Admissions, Beds, Pharmacy, Laboratory, Billing | 109 passed | Discharge workflow; bed allocation/release; balance = total − paid |
| B | Fleet | Vehicles, Drivers, Trips, Maintenance, Fuel records, Vehicle assignments | 94 passed | Trip start/complete/cancel; trips allocate vehicle + driver; maintenance puts vehicle in "maintenance" |
| C | LMS | Students, Teachers, Courses, Lessons, Attendance, Assignments, Examinations | 82 passed | Attendance states; courses admin-managed |
| D | E-commerce | Products, Shopping cart, Customers, Orders, Payments, Inventory, Delivery tracking | 88 passed | Order paid/ship/deliver/cancel; delivery date order |
| E | Project mgmt | Projects, Tasks, Teams, Milestones, Comments | 73 passed | "deadlines" → upcoming-deadline metrics; "progress" → 0–100 % field + average |
| F | Apiary (unfamiliar) | Hives, Queens, Inspections, Honey harvests, Swarm reports, Reports | 75 passed | beekeeper role; swarm capture/lost workflow |

All six: QA passed, requirement coverage passed with 0 missing items, deploy healthy including the
application-identity probe; no Product/Category/Contact/Booking/Employee/Room records leaked into A–C, E, F.
An additional unfamiliar prompt (coral reef restoration) is covered at specification level.

The user's own prompts (generated + executed): MediCare 140 tests passed and 194/194 specification items
covered (printing reported unsupported); MediCare correction prompt 172 passed and 195/195 items covered;
ShopSphere 52 passed.
Browser check (verified): the regenerated MediCare and correction-prompt apps show the requested
modules, the requested dashboard figures (patient count, doctor count, today's appointments, admitted
patients, available/occupied beds, pending bills, recent activity), navy sidebar and teal accent; a
Discharge action released its bed and the "Available beds" figure changed accordingly.

## 9. Test-suite results — verified

* Platform Python suite: **161 passed** (includes the six full-pipeline runs, a concurrent two-pipeline
  isolation test and the existing e2e/regression tests).
* Platform frontend: production build succeeded; Vitest **15 passed**.
* Generated apps for all 15 stored/benchmark prompts: every generated suite passed (35–172 tests each).
* Generated frontends built with Vite: MediCare and correction-prompt apps (verified); the others were
  not built in the automated runs.

## 10. Remaining limitations

* The deterministic extractor is heuristic English parsing. Unusual phrasing can still miss or
  misread a requirement; misses are visible in `ambiguities`/QA coverage rather than hidden, but the
  coverage check can only verify what was extracted.
* LLM mode was **not** exercised (no API key available); its instructions and post-processing were
  updated but are untested against a real model.
* Typical attributes for vague entities come from the enrichment lexicon (reported as ambiguities);
  completely unknown records get generic name/description or date/notes fields.
* Duplicate prevention is enforced in the API (not a DB constraint) so concurrent requests could
  race; allocation is status-based (one holder per resource, no capacity counting).
* The correction round re-runs deterministic agents, so it repairs missing/corrupted output but cannot
  invent logic the generator does not support.
* Not generated (reported as unsupported): printing/PDF, file uploads, payment processing, storefront
  marketing pages, checkout converting cart lines into order lines, maps/GPS, chat, notifications.
* Existing projects in `workspace/projects` were **not** modified or regenerated; regenerate them (new
  run or iteration) to get the corrected output.

## 11. Verified vs assumed

Verified by execution: everything in sections 8 and 9, the root-cause reproduction (stored runs and
six-prompt reproduction against the old analyser), the live browser checks listed above.
Assumptions / not verified: LLM-mode behaviour; Docker image builds (Docker not installed); Vite builds
of generated frontends other than the two listed; behaviour on prompts in languages other than English.
