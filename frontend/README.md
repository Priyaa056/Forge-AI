# FORGE AI frontend

## Project overview

This source export preserves the current FORGE AI landing page, robot mascot, animations, light/dark theme, and login/sign-up screens, including form validation and password visibility controls.

**Current state:** authentication is not connected. Forms explicitly report that sign-in is unavailable; they do not create accounts or authenticate users. Agent orchestration, a builder workspace, live generated-app previews, project history, and app ZIP generation are not implemented workflows. Homepage examples are illustrations, not real backend results. This export does not add mock services, a backend, or database/authentication services.

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

Open **http://127.0.0.1:3000**. Existing pages: `/`, `/login`, `/signup`. Keep the terminal running; Ctrl+C stops it. Source changes update the page automatically.

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

**No environment variables are required by the current frontend.** `.env.example` contains only an optional public localhost placeholder for future integration:

| Variable | Intended use | Current status |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Base URL of your existing FastAPI service | Not read by current code; setting it alone does not connect the backend |

When connecting the real backend, set your local URL in `.env.local` and read it through `import.meta.env.VITE_API_BASE_URL`. Restart development after changing environment values. Vite exposes `VITE_` values to the browser: **never store passwords, private API keys, tokens, or other secrets in them**. Keep backend secrets in FastAPI. Real `.env` files must not be committed or exported.

## Backend integration requirements

Run your existing Python FastAPI backend separately. No Python backend is included or created here. Keep the frontend in its own folder so extracting it cannot overwrite your backend.

Confirm your backend's actual API contract before wiring the frontend:

- Base URL and real login, registration, logout/session, and recovery endpoint paths.
- Request fields, response shapes, error handling, session expiry, and refresh behavior.
- Whether authentication uses secure cookies or bearer tokens.
- Actual agent execution and progress interfaces, including SSE/WebSocket formats if supported.
- Actual generated-app preview, history, and source-download endpoints.

Endpoint paths are deliberately **not guessed**. `src/components/AuthForm.tsx` contains the current disconnected submission handler; connect it to the real login/registration endpoints while keeping its design and validation. Add a browser-safe API client once the contract is known. Other advertised backend workflows need their actual screens and integration; this source does not claim they already exist.

For browser-to-FastAPI calls, enable CORS on the existing backend for the exact frontend origin, for example `http://127.0.0.1:3000`. `http://localhost:3000` is a different origin and needs separate allowance if used. Allow the methods and headers needed by the real API. Cookie authentication also requires explicit origins (not `*`), backend credential support, appropriate cookie settings, and frontend requests with `credentials: "include"`. Do not expose privileged backend credentials to browser code.

## Source layout

```text
src/
  assets/          Robot and local media
  components/     Branding, auth forms, UI components
  hooks/          Shared hooks
  lib/            Utilities and existing error handling
  routes/         Home, login, signup, root layout
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

## Export verification

An isolated exported copy passed dependency installation, `npm run build`, and the existing automated routing test on Linux with Node.js 22.23.4. All three current pages also loaded in a browser without page errors; sign-up correctly reported that authentication is not connected. The build completed with non-fatal bundler/dependency warnings. Windows execution itself was not tested; the Windows commands above use the same project scripts. No deployment was performed.
