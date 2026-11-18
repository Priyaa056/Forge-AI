# FORGE AI: Autonomous Multi-Agent Full-Stack Application Builder

FORGE AI turns a natural-language application idea into a **working, tested, deployable full-stack
application** (React + FastAPI + SQLAlchemy/PostgreSQL + JWT auth + Docker). Seven specialised
agents collaborate through versioned, validated artifacts under a central orchestrator. The FORGE AI
web app (our original Lovable design) shows every step live, and stable versions can be rolled back.

| Objective | Implemented as |
|---|---|
| 1. Multi-agent orchestration | 7 agents (PM, UI, Backend, DB, Auth, QA, Deploy), dependency-ordered pipeline, artifact contracts with lineage, cross-agent contract validation, retries, failure isolation (`backend/services/pipeline.py`) |
| 2. Full-stack generation | Each agent writes the project files it owns. QA **executes** the generated test suite and a real `vite build`. Deploy starts the app and health-checks it. Live preview (`backend/codegen/`, `backend/agents/`) |
| 3. Monitoring, logging and rollback | Structured JSONL events, live progress API and web workspace, per-agent logs, artifact versioning, persisted project/run history, checksum-verified promotion and rollback of files **and** artifacts (`backend/monitoring/`, `backend/services/project_store.py`) |

## Architecture

```
frontend/ (Lovable design:          --HTTP-->  backend/main.py (FastAPI platform API: accounts,
  TanStack Start, React 19, Tailwind 4)          projects, runs, artifacts, previews)
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
| **UI** | requirements | `ui_spec.json`: pages, routes, forms, components, API requirements, theme | generated app's `frontend/`: React 18 + Vite SPA with routing, layout, CRUD pages with search/filters/pagination, dashboard, admin dashboard |
| **Backend** | requirements, UI spec | `api_spec.json`: endpoints, schemas, permissions, row-level scopes. **Fails if the UI needs an endpoint the API does not provide.** | `backend/app/main.py`, `schemas.py`, `routers/*` (validation, ownership, reference integrity, 409 on conflicts) |
| **Database** | requirements, API spec | `database_schema.json`: tables, columns, FKs, CHECK/UNIQUE constraints, indexes. **Fails if an API field has no column.** | `models.py` (SQLAlchemy 2), `database.py`, `migrations/001_initial_schema.sql` (PostgreSQL) |
| **Auth** | requirements, API spec, DB schema | `auth_spec.json`: PBKDF2 policy, JWT strategy, RBAC matrix derived from endpoint permissions | `security.py` (hashing, HS256 JWT, `require_permission`), auth + user-management routers, admin seed, React auth context and login/register pages |
| **QA** | all specs + files | `qa_report.json`: executed checks, per-test results, classified errors, responsible agent, repair recommendation | `backend/tests/*` (auth, CRUD, validation, search/filter, RBAC, ownership isolation, references) |
| **Deploy** | specs + QA report | `deployment_report.json`: readiness checks, live health checks, instructions | `Dockerfile`s, `nginx.conf`, `docker-compose.yml` (PostgreSQL), `.env.example`, `README.md` |

QA runs real checks: Python syntax, application import and route registration, UI↔API contract,
PostgreSQL DDL compilation, the generated pytest suite, frontend import resolution, and `vite build`.
A failing check fails the QA stage, Deploy is skipped, and the previous stable version stays live.

### Run lifecycle, versions and rollback
1. `POST /api/projects` creates a project (owned by the signed-in user) and starts a run in the background. The web app polls status and events every second.
2. Agent states: `PENDING → RUNNING → COMPLETED | FAILED`, `RETRYING` (one retry for transient errors), `SKIPPED` (downstream of a failure).
3. A fully successful run is **promoted**: its snapshot is verified against `forge_manifest.json` (SHA-256 per file) and copied atomically to `current/`, creating version *n*.
4. A failed run never touches `current/`. **Rollback** to any earlier stable run re-materialises that snapshot (checksum-verified) **and** restores all seven artifacts as new versions (history is never deleted). Rollback to a failed run, or to a tampered snapshot, is rejected.
5. **Preview** runs the active version as a real process (API + built frontend) on a local port with local-only admin credentials.

### Web app and accounts
`frontend/` is the original Lovable FORGE AI frontend (landing page, robot mascot, light/dark theme,
login/sign-up), now connected to the platform API. Signed-in users get:
- **Dashboard** (`/app`): project history with live status, builds run, live versions.
- **New project** (`/app/new`): natural-language prompt, optional test-mode failure injection.
- **Workspace** (`/app/projects/<id>`): the seven agents' live status, activity log, artifact viewer,
  generated files, executed QA and deploy reports, embedded live preview of the generated app, version
  history with rollback, new iterations and ZIP download.

Platform accounts use PBKDF2-hashed passwords (`workspace/users.json`) and signed bearer tokens
(`FORGE_SECRET_KEY`, or a key generated once into the workspace). Every project endpoint checks
ownership; other users' projects return 404. Projects created before accounts existed are assigned to
the first account registered on the installation.

### LLM usage and generation modes
The PM agent (requirement analysis) and UI agent (visual identity) call **Google Gemini** (the
project's existing provider) when `USE_LLM=true` and `GOOGLE_API_KEY` are set. LLM output is parsed,
schema-validated and normalised; on failure the agent retries once and then falls back **visibly** to
the deterministic analyzer. Without a key, FORGE AI runs in **deterministic mode**: a prompt-driven
analyzer with a domain knowledge base (about 50 entity types, 20 domains, relation rules, generic noun
extraction). Every artifact and agent card records its `generation_mode`. Code is rendered from the
validated specs by templates, which keeps the generated apps runnable and testable.

## Setup

Requirements: Python 3.11+, Node.js 22.12+ (the Lovable frontend requires it; also used for generated-frontend builds). Docker is optional.

```bash
pip install -r requirements.txt
cp .env.example backend/.env        # optional: set USE_LLM=true and GOOGLE_API_KEY
cd frontend && npm ci && cd ..
```

## Run

```bash
python -m uvicorn backend.main:app --port 8000
```
```bash
cd frontend && npm run dev -- --host 127.0.0.1 --port 3000     # http://127.0.0.1:3000
```

The first generation installs a shared React/Vite toolchain into `workspace/node_modules` (about 30 s, once).
Then a typical generation takes about 10 s. Open the web app, sign up, and create a project.
The frontend calls the API at `VITE_API_BASE_URL` (default `http://127.0.0.1:8000`).

Docker alternative for the platform itself: `docker compose up --build` (web app :3000, API :8000).

## Tests

```bash
python -m pytest
```
```bash
cd frontend && npm run test
```
135 Python tests cover platform accounts and project ownership, the PM analysis, the LLM integration (fake client), code generation, cross-agent contracts,
orchestration semantics, the project store and rollback, the platform API lifecycle, and real end-to-end
generation including a `vite build` and a deliberately broken backend that QA must catch.
15 frontend tests cover routing of every page and the API client (tokens, 401 handling, errors).

## Repository layout
```
backend/agents/        seven agents + PM analysis
backend/codegen/       blueprint + writers (frontend, backend, db, auth, qa, deploy)
backend/schemas/       Pydantic contracts for every artifact
backend/artifacts/     artifact store, manager, context, rollback manager
backend/monitoring/    execution events, JSONL logger, queries
backend/services/      pipeline, run manager, project store, preview, toolchain, failure classifier, self-healing
backend/llm/           Gemini client + JSON extraction
backend/auth/          platform accounts (password hashing, tokens, user store)
frontend/              FORGE AI web app: original Lovable design + workspace screens (not a generated app)
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
- **Accounts:** no password recovery or e-mail verification yet; the session token is kept in the browser's
  `localStorage` and expires after 12 hours.
- **New screens:** the dashboard, new-project and workspace screens did not exist in the Lovable export.
  They are composed from its existing patterns and tokens, not from a separate design.
