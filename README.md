# FORGE AI: Autonomous Multi-Agent Full-Stack Application Builder

FORGE AI turns a natural-language application idea into a **working, tested, deployable full-stack
application** (React + FastAPI + SQLAlchemy/PostgreSQL + JWT auth + Docker). Seven specialised
agents collaborate through versioned, validated artifacts under a central orchestrator. A monitoring
dashboard shows every step, and stable versions can be rolled back.

| Objective | Implemented as |
|---|---|
| 1. Multi-agent orchestration | 7 agents (PM, UI, Backend, DB, Auth, QA, Deploy), dependency-ordered pipeline, artifact contracts with lineage, cross-agent contract validation, retries, failure isolation (`backend/services/pipeline.py`) |
| 2. Full-stack generation | Each agent writes the project files it owns. QA **executes** the generated test suite and a real `vite build`. Deploy starts the app and health-checks it. Live preview (`backend/codegen/`, `backend/agents/`) |
| 3. Monitoring, logging and rollback | Structured JSONL events, live progress API and dashboard, per-agent logs, artifact versioning, persisted project/run history, checksum-verified promotion and rollback of files **and** artifacts (`backend/monitoring/`, `backend/services/project_store.py`) |

## Architecture

```
dashboard/ (React+TS+Tailwind)  --HTTP-->  backend/main.py (FastAPI platform API)
                                               |
                                    services/run_manager.py   (background runs, promotion)
                                               |
                                    services/pipeline.py      (ForgePipeline orchestrator)
     PM -> UI -> Backend -> DB -> Auth -> QA -> Deploy        (backend/agents/*)
       |     each agent: load upstream artifacts of THIS run -> generate spec -> validate (Pydantic)
       |                 -> save spec JSON -> write owned files (backend/codegen/*)
       v
artifacts/ (versioned, lineage)   logs/pipeline_execution.jsonl   projects/<id>/runs/<run>/{specs,app}
                                                                   projects/<id>/current  (stable version)
```

### The seven agents

| Agent | Consumes | Produces (artifact) | Writes (files it owns) |
|---|---|---|---|
| **PM** | user prompt | `requirements.json`: entities, fields, relations, access policies, roles, functional/non-functional requirements, dependencies, development plan | `docs/REQUIREMENTS.md` |
| **UI** | requirements | `ui_spec.json`: pages, routes, forms, components, API requirements, theme | `frontend/` React 18 + Vite SPA: routing, layout, CRUD pages with search/filters/pagination, dashboard, admin dashboard |
| **Backend** | requirements, UI spec | `api_spec.json`: endpoints, schemas, permissions, row-level scopes. **Fails if the UI needs an endpoint the API does not provide.** | `backend/app/main.py`, `schemas.py`, `routers/*` (validation, ownership, reference integrity, 409 on conflicts) |
| **Database** | requirements, API spec | `database_schema.json`: tables, columns, FKs, CHECK/UNIQUE constraints, indexes. **Fails if an API field has no column.** | `models.py` (SQLAlchemy 2), `database.py`, `migrations/001_initial_schema.sql` (PostgreSQL) |
| **Auth** | requirements, API spec, DB schema | `auth_spec.json`: PBKDF2 policy, JWT strategy, RBAC matrix derived from endpoint permissions | `security.py` (hashing, HS256 JWT, `require_permission`), auth + user-management routers, admin seed, React auth context and login/register pages |
| **QA** | all specs + files | `qa_report.json`: executed checks, per-test results, classified errors, responsible agent, repair recommendation | `backend/tests/*` (auth, CRUD, validation, search/filter, RBAC, ownership isolation, references) |
| **Deploy** | specs + QA report | `deployment_report.json`: readiness checks, live health checks, instructions | `Dockerfile`s, `nginx.conf`, `docker-compose.yml` (PostgreSQL), `.env.example`, `README.md` |

QA runs real checks: Python syntax, application import and route registration, UI↔API contract,
PostgreSQL DDL compilation, the generated pytest suite, frontend import resolution, and `vite build`.
A failing check fails the QA stage, Deploy is skipped, and the previous stable version stays live.

### Run lifecycle, versions and rollback
1. `POST /api/projects` creates a project and starts a run in the background. The dashboard polls status and events.
2. Agent states: `PENDING → RUNNING → COMPLETED | FAILED`, `RETRYING` (one retry for transient errors), `SKIPPED` (downstream of a failure).
3. A fully successful run is **promoted**: its snapshot is verified against `forge_manifest.json` (SHA-256 per file) and copied atomically to `current/`, creating version *n*.
4. A failed run never touches `current/`. **Rollback** to any earlier stable run re-materialises that snapshot (checksum-verified) **and** restores all seven artifacts as new versions (history is never deleted). Rollback to a failed run, or to a tampered snapshot, is rejected.
5. **Preview** runs the active version as a real process (API + built frontend) on a local port with local-only admin credentials.

### LLM usage and generation modes
The PM agent (requirement analysis) and UI agent (visual identity) call **Google Gemini** (the
project's existing provider) when `USE_LLM=true` and `GOOGLE_API_KEY` are set. LLM output is parsed,
schema-validated and normalised; on failure the agent retries once and then falls back **visibly** to
the deterministic analyzer. Without a key, FORGE AI runs in **deterministic mode**: a prompt-driven
analyzer with a domain knowledge base (about 50 entity types, 20 domains, relation rules, generic noun
extraction). Every artifact and agent card records its `generation_mode`. Code is rendered from the
validated specs by templates, which keeps the generated apps runnable and testable.

## Setup

Requirements: Python 3.11+, Node.js 18+ (for generated-frontend builds and the dashboard). Docker is optional.

```bash
pip install -r requirements.txt
cp .env.example backend/.env        # optional: set USE_LLM=true and GOOGLE_API_KEY
cd dashboard && npm install && cd ..
```

## Run

```bash
python -m uvicorn backend.main:app --port 8000
```
```bash
cd dashboard && npm run dev          # http://localhost:5173 (proxies /api to :8000)
```

The first generation installs a shared React/Vite toolchain into `workspace/node_modules` (about 30 s, once).
Then a typical generation takes about 10 s.

Docker alternative for the platform itself: `docker compose up --build` (dashboard :3000, API :8000).

## Tests

```bash
python -m pytest
```
128 tests cover the PM analysis, the LLM integration (fake client), code generation, cross-agent contracts,
orchestration semantics, the project store and rollback, the platform API lifecycle, and real end-to-end
generation including a `vite build` and a deliberately broken backend that QA must catch.

## Repository layout
```
backend/agents/        seven agents + PM analysis
backend/codegen/       blueprint + writers (frontend, backend, db, auth, qa, deploy)
backend/schemas/       Pydantic contracts for every artifact
backend/artifacts/     artifact store, manager, context, rollback manager
backend/monitoring/    execution events, JSONL logger, queries
backend/services/      pipeline, run manager, project store, preview, toolchain, failure classifier, self-healing
backend/llm/           Gemini client + JSON extraction
dashboard/             FORGE AI platform dashboard (not a generated app)
docs/                  implementation assessment and architecture notes
workspace/             (git-ignored) generated projects, artifacts, logs
```

## Known limitations
- **Docker images are not built or run by FORGE AI on this machine** (Docker is not installed here). Deploy
  validates the Docker/Compose configuration and health-checks the app as a local process. Reports
  state `container_build_verified: false`.
- **PostgreSQL is not exercised live here.** Generated models compile to PostgreSQL DDL (checked by QA), and the
  compose file provisions PostgreSQL. Local tests and previews use SQLite through the same SQLAlchemy code.
- **The LLM path is implemented and unit-tested with a fake client.** It has not been run against the live Gemini
  API in this environment (no key available). Without a key, the deterministic analyzer is used and labelled.
- **Generated apps are CRUD-centric:** entities, relations, roles, ownership, search/filter, dashboards. Domain
  workflows such as checkout/payment, e-mail or file upload are not generated.
- **Iterations regenerate the whole application from the new prompt** rather than patching it. In LLM mode the
  previous requirements are passed as context.
- **Previews run on random local ports** and are reachable only from the machine running the platform.
