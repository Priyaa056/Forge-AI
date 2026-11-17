"""Deploy Agent: prepares the validated application for execution and deployment.

* Writes Dockerfiles, nginx config, docker-compose (PostgreSQL), .env.example and README.
* Validates configuration: env vars referenced by the code are documented, Docker COPY sources exist,
  compose file parses, requirements include the runtime packages, migration exists.
* Performs a live health check: starts the generated backend (serving the built frontend) as a real
  process, probes /health, auth and admin endpoints, then stops it.

Output: ``deployment_report.json`` (DeployOutput). Docker images are only reported as built if they were.
"""

import json
import re
import secrets
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.agents.base_agent import BaseAgent
from backend.artifacts.artifact_context import ArtifactContext
from backend.codegen.blueprint import build_blueprint
from backend.codegen.deploy_writer import REQUIRED_ENV, write_deploy_files
from backend.exceptions import GenerationError
from backend.schemas.auth_schema import AuthOutput
from backend.schemas.backend_schema import BackendOutput
from backend.schemas.deploy_schema import DeployOutput
from backend.schemas.pm_schema import PMOutput
from backend.schemas.qa_schema import QAOutput
from backend.services.app_runner import GeneratedAppProcess, http_request

AGENT = "deploy"


class DeployAgent(BaseAgent[DeployOutput]):
    stage_name = AGENT

    def __init__(
        self,
        pm_output_path: str = "outputs/pm_output.json",
        backend_output_path: str = "outputs/backend_output.json",
        db_output_path: str = "outputs/db_output.json",
        auth_output_path: str = "outputs/auth_output.json",
        ui_output_path: str = "outputs/ui_output.json",
        qa_output_path: str = "outputs/qa_output.json",
        output_filepath: str = "outputs/deploy_output.json",
        artifact_context: Optional[ArtifactContext] = None,
        project: Optional[Any] = None,
        log_fn=None,
        run_health_check: bool = True,
    ):
        super().__init__(output_schema_cls=DeployOutput, output_filepath=output_filepath,
                         artifact_context=artifact_context, project=project, log_fn=log_fn)
        self.paths = {"pm": pm_output_path, "backend": backend_output_path, "auth": auth_output_path, "qa": qa_output_path}
        self.run_health_check = run_health_check
        self.generation_mode = "execution"

    def load_inputs(self) -> None:
        self.pm_data = self.load_upstream("pm", PMOutput, self.paths["pm"])
        self.backend_data = self.load_upstream("backend", BackendOutput, self.paths["backend"])
        self.auth_data = self.load_upstream("auth", AuthOutput, self.paths["auth"])
        self.qa_data = self.load_upstream("qa", QAOutput, self.paths["qa"])
        if self.project is None:
            raise GenerationError("Deploy requires the generated project files")
        if self.qa_data.status != "passed":
            raise GenerationError(f"QA status is '{self.qa_data.status}'; refusing to prepare an untested build")

    def _readiness(self, root: Path) -> List[Dict[str, str]]:
        checks: List[Dict[str, str]] = []

        def add(name, ok, details):
            checks.append({"name": name, "status": "passed" if ok else "failed", "details": details})

        env_example = (root / ".env.example").read_text(encoding="utf-8")
        documented = set(re.findall(r"^([A-Z][A-Z0-9_]+)=", env_example, re.M))
        code = "\n".join(p.read_text(encoding="utf-8") for p in (root / "backend" / "app").rglob("*.py"))
        referenced = set(re.findall(r"os\.getenv\(\s*['\"]([A-Z0-9_]+)['\"]", code))
        referenced -= {"FRONTEND_DIST", "PASSWORD_HASH_ITERATIONS", "ADMIN_NAME"}
        missing = sorted(referenced - documented)
        add("Environment variables documented in .env.example", not missing,
            f"Missing: {', '.join(missing)}" if missing else f"{len(referenced)} variables: {', '.join(sorted(referenced))}")

        leaked = [line for line in env_example.splitlines()
                  if re.match(r"^(SECRET_KEY|ADMIN_PASSWORD|POSTGRES_PASSWORD)=", line) and "CHANGE_ME" not in line]
        add("No real secrets in .env.example", not leaked, "Secrets are placeholders" if not leaked else "; ".join(leaked))

        problems = []
        for dockerfile in (root / "backend" / "Dockerfile", root / "frontend" / "Dockerfile"):
            for src in re.findall(r"^COPY\s+(?!--from)(\S+)\s+\S+", dockerfile.read_text(encoding="utf-8"), re.M):
                if src != "." and not (dockerfile.parent / src).exists():
                    problems.append(f"{dockerfile.parent.name}/Dockerfile copies missing '{src}'")
        add("Dockerfile build contexts", not problems, "; ".join(problems) or "All COPY sources exist")

        compose_text = (root / "docker-compose.yml").read_text(encoding="utf-8")
        try:
            import yaml  # type: ignore

            compose = yaml.safe_load(compose_text)
            services = set((compose or {}).get("services", {}))
            ok = {"db", "backend", "frontend"} <= services
            add("docker-compose.yml parses (db, backend, frontend)", ok, f"services: {', '.join(sorted(services))}")
        except ImportError:
            ok = all(f"\n  {svc}:" in compose_text for svc in ("db", "backend", "frontend"))
            add("docker-compose.yml services present", ok, "PyYAML not installed; structural check only")
        except Exception as exc:  # yaml error
            add("docker-compose.yml parses", False, str(exc))

        requirements = (root / "backend" / "requirements.txt").read_text(encoding="utf-8").lower()
        needed = [pkg for pkg in ("fastapi", "uvicorn", "sqlalchemy", "psycopg2-binary") if pkg not in requirements]
        add("Runtime dependencies pinned in requirements.txt", not needed, f"Missing: {', '.join(needed)}" if needed else "fastapi, uvicorn, sqlalchemy, psycopg2-binary")

        migration = root / "backend" / "migrations" / "001_initial_schema.sql"
        add("PostgreSQL migration present", migration.is_file(), str(migration.relative_to(root)) if migration.is_file() else "missing")

        dist = root / "frontend" / "dist" / "index.html"
        add("Frontend production bundle", dist.is_file(), "frontend/dist built by QA" if dist.is_file() else "frontend/dist missing")
        return checks

    def _health_check(self, root: Path) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        logs: List[str] = []
        runtime = Path(tempfile.mkdtemp(prefix="forge_deploy_"))
        admin_password = "Hc-" + secrets.token_urlsafe(10) + "1"
        proc = GeneratedAppProcess(root, data_dir=runtime, admin_email="healthcheck-admin@example.com",
                                   admin_password=admin_password)
        started = proc.start(timeout=60)
        logs.append(f"Started generated backend on {proc.url}: {'ok' if started else 'FAILED'}")

        def probe(name, path, expected, method="GET", body=None, token=None):
            status, text, ms = http_request(proc.url + path, method=method, body=body, token=token)
            healthy = status == expected
            results.append({"endpoint": name, "status_code": status, "status": "healthy" if healthy else "unhealthy",
                            "response_time_ms": round(ms, 1), "message": f"expected {expected}"})
            return status, text

        try:
            if not started:
                logs.append(proc.read_log()[-2000:])
                results.append({"endpoint": "GET /health", "status_code": 0, "status": "unhealthy",
                                "response_time_ms": 0.0, "message": "Server did not start"})
                return {"results": results, "logs": logs, "url": proc.url}
            probe("GET /health", "/health", 200)
            probe("GET /api/auth/me (no token -> 401)", "/api/auth/me", 401)
            status, text = probe("POST /api/auth/login (seeded admin)", "/api/auth/login", 200, "POST",
                                 {"email": "healthcheck-admin@example.com", "password": admin_password})
            token = json.loads(text).get("access_token") if status == 200 else None
            if token:
                probe("GET /api/admin/stats (admin token)", "/api/admin/stats", 200, token=token)
                first = build_blueprint(self.pm_data).entities[0]
                probe(f"GET {first.api_path} (admin token)", first.api_path, 200, token=token)
            if (root / "frontend" / "dist" / "index.html").is_file():
                status, text = probe("GET / (frontend bundle)", "/", 200)
                if status == 200 and "<div id=\"root\">" not in text:
                    results[-1]["status"] = "unhealthy"
                    results[-1]["message"] = "Response is not the SPA index.html"
        finally:
            proc.stop()
            logs.append("Stopped health-check server")
            shutil.rmtree(runtime, ignore_errors=True)
        return {"results": results, "logs": logs, "url": proc.url}

    def generate(self) -> Dict[str, Any]:
        bp = build_blueprint(self.pm_data)
        root = self.project.root
        qa_summary = {"tests_passed": self.qa_data.tests_passed, "tests_run": self.qa_data.tests_run}
        files = write_deploy_files(bp, self.project, self.backend_data.model_dump(), self.auth_data.model_dump(), qa_summary)
        self.generated_files = files
        self.log(f"Wrote deployment configuration: {', '.join(files)}")

        readiness = self._readiness(root)
        for c in readiness:
            self.log(f"[{'PASS' if c['status'] == 'passed' else 'FAIL'}] {c['name']}: {c['details'][:150]}",
                     "info" if c["status"] == "passed" else "warning")

        docker = shutil.which("docker") is not None
        readiness.append({"name": "Docker CLI available", "status": "passed" if docker else "skipped",
                          "details": "docker found" if docker else "Docker not installed on this machine; images not built"})

        health = {"results": [], "logs": [], "url": None}
        if self.run_health_check:
            health = self._health_check(root)
            for r in health["results"]:
                self.log(f"Health check {r['endpoint']}: {r['status_code']} ({r['status']}, {r['response_time_ms']} ms)",
                         "info" if r["status"] == "healthy" else "warning")

        failed = [c for c in readiness if c["status"] == "failed"] + [r for r in health["results"] if r["status"] != "healthy"]
        ready = not failed and (bool(health["results"]) or not self.run_health_check)
        return {
            "project_name": bp.project_name,
            "status": "success" if ready else "failed",
            "environment": "development",
            "live_url": health["url"],
            "docker_config": {"backend_image": f"{bp.slug}-backend:latest", "frontend_image": f"{bp.slug}-frontend:latest",
                              "db_image": "postgres:16-alpine", "compose_file": "docker-compose.yml",
                              "exposed_ports": {"backend": 8000, "frontend": 8080, "postgres": 5432}},
            "health_checks": health["results"],
            "readiness_checks": readiness,
            "required_env_vars": REQUIRED_ENV,
            "docker_available": docker,
            "container_build_verified": False,
            "deployment_ready": ready,
            "deployment_timestamp": datetime.now(timezone.utc).isoformat(),
            "instructions": [
                "Local: cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8000",
                "Local frontend: cd frontend && npm install && npm run dev",
                "Docker: cp .env.example .env (set secrets) && docker compose up --build",
            ],
            "logs": health["logs"],
            "affected_component": None if ready else "deployment",
        }

    def emit_code(self, output: DeployOutput) -> List[str]:
        return self.generated_files

    @staticmethod
    def is_success(output: DeployOutput) -> bool:
        return output.status == "success" and output.deployment_ready
