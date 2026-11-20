# FORGE AI frontend

## Project overview

This source export preserves the current FORGE AI landing page, robot mascot, animations, light/dark theme, and login/sign-up screens, including form validation and password visibility controls.

**Current state (integrated with the FORGE AI platform API in `../backend`):** the original Lovable design is unchanged and is now the FORGE AI web app. Sign-up and log-in create and use real platform accounts. Signed-in users get a dashboard with their project history, a new-project screen, and a project workspace that shows live progress of the seven agents, the activity log, each agent's artifact, the generated source files, executed QA and deployment reports, an embedded live preview of the generated application, version history with rollback, a ZIP download and push to GitHub. Projects can be refined with plain-English change requests (with a plan preview before applying), and the dashboard shows build statistics. The homepage's hero and "Generated preview" mock-ups remain illustrations. Password recovery is not implemented.

Screens added for the signed-in area (`/app`, `/app/new`, `/app/projects/$projectId`) did not exist in the Lovable export; they are composed only from the export's existing patterns (hero workspace frame, agent list with status dots, cards, buttons, form fields, tokens) so they look like the original design.

## Technology stack

- React 19 and TypeScript
- TanStack Start v1 and TanStack Router (server-rendered React application)
- Vite (exact version in `package.json`)
- Tailwind CSS v4, shadcn/Radix UI components, Lucide icons
- TanStack Query
- Vitest and Testing Library
- Nitro and the existing shared Vite configuration for production output

All dependencies are declared in `package.json`. `bun.lock` preserves the existing Bun resolution; the export also includes `package-lock.json` for repeatable npm installation. Installed dependencies are not bundled in the ZIP.

## Installation on Windows

1. Install **Node.js 22.12 or newer** and npm (Node.js 24 LTS recommended).
2. Extract the ZIP into a **new folder** on your PC, not over another project. A short path such as `C:\Projects\forge-ai-frontend` helps avoid Windows path-length problems.
3. Open PowerShell in the extracted folder containing `package.json`.
4. Install dependencies:

```powershell
npm ci
```

Use `npm install` instead if you intentionally change dependencies. Installation needs internet access to the npm registry, including the `@lovable.dev` scope. No Lovable account, GitHub connection, cloning, or cloud-service setup is required. Alternatively, with Bun installed, use `bun install --frozen-lockfile`, then the same scripts with `bun run`.

## Local development

```powershell
Copy-Item .env.example .env.local
npm run dev -- --host 127.0.0.1 --port 3000
```

Open **http://127.0.0.1:3000**. Pages: `/`, `/login`, `/signup`, and (signed in) `/app`, `/app/new`, `/app/projects/<id>`. Start the platform API first (`python -m uvicorn backend.main:app --port 8000` from the repository root). Keep the terminal running; Ctrl+C stops it. Source changes update the page automatically.

Google Fonts requires internet access for the exact intended fonts; offline use falls back to system fonts. The robot image and all existing local assets are included.

## Production build and local preview

```powershell
npm run build
npm run preview -- --host 127.0.0.1 --port 3000
```

Generated output goes to `dist` and/or `.output` according to the existing configuration and is excluded from the source ZIP. Preview is a local build check, not a production hosting service. This is a TanStack Start application, not a plain static HTML bundle: future hosting must support its server-rendering output. The existing Nitro configuration targets Cloudflare output; changing the hosting target requires separate configuration. None of these commands publishes or deploys the app.

Other commands:

```powershell
npm run test
npm run lint
```

`npm run test:watch` runs tests interactively. `npm run format` reformats files and is not required for startup.

## Environment variables required

**No environment variables are required for local development.**

| Variable | Use | Default |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Base URL of the FORGE AI platform API, read in `src/lib/api/client.ts` | `http://127.0.0.1:8000` |

To point the app at another API, set the value in `.env.local` and restart development. Vite exposes `VITE_` values to the browser: **never store passwords, private API keys, tokens, or other secrets in them**. Keep backend secrets in FastAPI. Real `.env` files must not be committed or exported.

## Backend integration requirements

The FastAPI platform API lives in `../backend` (run it separately). The contract the frontend uses:

| Area | Endpoints |
| --- | --- |
| Accounts | `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`: bearer tokens (`Authorization: Bearer ...`), stored in `localStorage` under `forge-token`; a 401 signs the user out |
| Platform | `GET /api/system` (generation mode, LLM provider, toolchain, fault injection), `GET /api/stats?days=` (dashboard statistics) |
| Projects & runs | `GET/POST /api/projects`, `GET/DELETE /api/projects/{id}`, `POST /api/projects/{id}/runs` (rebuild), `GET .../runs/{run}` (polled every second while a build runs), `GET .../runs/{run}/events`, `GET /api/projects/{id}/events` |
| Refinement | `POST /api/projects/{id}/refine/preview` (plan preview), `POST /api/projects/{id}/refine` (apply a change or an approved plan), `GET .../runs/{run}/changes` |
| Artifacts & reports | `GET /api/artifacts/{id}`, `GET .../runs/{run}/specs/pm`, `GET .../runs/{run}/specs/qa`, `GET .../runs/{run}/specs/deploy` |
| Files & output | `GET .../runs/{run}/files`, `GET .../runs/{run}/files/content?path=`, `GET .../runs/{run}/download` (ZIP; `run` may be `current`), `POST /api/projects/{id}/github/push` |
| Versions | `POST /api/projects/{id}/rollback` |
| Preview | `GET .../preview`, `POST .../preview/start`, `POST .../preview/stop` |

API access is kept out of the UI components: `src/lib/api/client.ts` (HTTP, token, errors), `src/lib/api/forge.ts` (typed endpoints), `src/lib/api/types.ts` (response shapes), `src/lib/auth.tsx` (session state). The API allows browser origins on `localhost` / `127.0.0.1` (any port) via CORS; no cookies are used.

## Source layout

```text
src/
  assets/          Robot and local media
  components/     Branding, auth forms, UI components
    app/          Signed-in screens' building blocks (agent pipeline, files, preview, reports, versions)
  hooks/          Shared hooks
  lib/            Utilities, existing error handling, agents metadata, session (auth.tsx)
    api/          Platform API client, typed endpoints and response types
  routes/         Home, login, signup, root layout, /app (dashboard, new project, workspace)
  test/           Automated tests
  router.tsx      Router configuration
  start.ts        Existing request middleware
  server.ts       Existing rendering/error wrapper
  styles.css      Design tokens, styling, animations
public/           Favicon and robots.txt
package.json      Dependencies and scripts
package-lock.json npm dependency lockfile
bun.lock          Existing Bun lockfile
.env.example      Placeholder-only configuration
vite.config.ts    Vite/TanStack Start configuration
vitest.config.ts  Test configuration
tsconfig.json    TypeScript configuration
```

All current components and assets are included, including unused UI components. Route definitions regenerate automatically; do not manually edit `src/routeTree.gen.ts`. Repository metadata, private workspace files, real environment files, installed dependencies, logs, and generated build output are excluded. No current design or functionality is removed.

## Production build for Docker / Node hosting

The shared Lovable Vite configuration targets Cloudflare by default. For a self-hosted Node server, build with Nitro's standard preset (no configuration change needed):

PowerShell:

```powershell
$env:NITRO_PRESET = "node-server"
npm run build
node .output/server/index.mjs     # PORT and HOST environment variables apply
```

bash:

```bash
NITRO_PRESET=node-server npm run build
node .output/server/index.mjs
```

`../docker/Dockerfile.frontend` does exactly this.

## Export verification (original Lovable export)

An isolated exported copy passed dependency installation, `npm run build`, and the existing automated routing test on Linux with Node.js 22.23.4. All three current pages also loaded in a browser without page errors; sign-up correctly reported that authentication is not connected. The build completed with non-fatal bundler/dependency warnings. Windows execution itself was not tested; the Windows commands above use the same project scripts. No deployment was performed.
