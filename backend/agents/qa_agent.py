"""QA Agent: generates and executes tests against the generated application.

Executed checks (all real, nothing is assumed to pass):
  1. Python syntax of every generated backend module
  2. Application import + route registration (FastAPI OpenAPI)
  3. UI <-> API contract: every endpoint the UI calls is registered by the backend
  4. PostgreSQL DDL compilation of the SQLAlchemy models
  5. Generated pytest suite (auth, CRUD, validation, search/filter, RBAC, ownership, references)
  6. Frontend import resolution
  7. Frontend production build (vite) when Node.js is available

Output: ``qa_report.json`` (QAOutput). Failures are classified (FailureClassifier) and mapped to the
responsible agent; the self-healing manager produces a repair recommendation.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.agents.base_agent import BaseAgent
from backend.artifacts.artifact_context import ArtifactContext
from backend.agents.requirement_coverage import check_requirement_coverage
from backend.codegen.blueprint import build_blueprint
from backend.codegen.qa_writer import write_test_files
from backend.config import env_flag
from backend.exceptions import GenerationError
from backend.schemas.auth_schema import AuthOutput
from backend.schemas.backend_schema import BackendOutput
from backend.schemas.db_schema import DBOutput
from backend.schemas.pm_schema import PMOutput
from backend.schemas.qa_schema import QAOutput
from backend.schemas.ui_schema import UIOutput
from backend.services.failure_classifier import FailureClassifier
from backend.services.self_healing import SelfHealingManager

AGENT = "qa"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

ROUTES_SCRIPT = """
import json, app.main as m
routes = sorted({(method, r.path) for r in m.app.routes for method in (getattr(r, 'methods', None) or []) if method not in ('HEAD', 'OPTIONS')})
print('FORGE_ROUTES=' + json.dumps(routes))
"""

DDL_SCRIPT = """
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable
from app.database import Base
import app.models  # noqa
count = 0
for table in Base.metadata.sorted_tables:
    str(CreateTable(table).compile(dialect=postgresql.dialect()))
    for index in table.indexes:
        str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    count += 1
print(f'FORGE_DDL_OK={count}')
"""

AGENT_FOR_COMPONENT = {
    "backend": "BackendAgent", "database": "DBAgent", "auth": "AuthAgent", "frontend": "UIAgent",
    "integration": "BackendAgent", "qa": "QAAgent",
}


class QAAgent(BaseAgent[QAOutput]):
    stage_name = AGENT

    def __init__(
        self,
        pm_output_path: str = "outputs/pm_output.json",
        backend_output_path: str = "outputs/backend_output.json",
        db_output_path: str = "outputs/db_output.json",
        auth_output_path: str = "outputs/auth_output.json",
        ui_output_path: str = "outputs/ui_output.json",
        output_filepath: str = "outputs/qa_output.json",
        artifact_context: Optional[ArtifactContext] = None,
        project: Optional[Any] = None,
        log_fn=None,
        run_frontend_build: Optional[bool] = None,
    ):
        super().__init__(output_schema_cls=QAOutput, output_filepath=output_filepath,
                         artifact_context=artifact_context, project=project, log_fn=log_fn)
        self.paths = {"pm": pm_output_path, "backend": backend_output_path, "db": db_output_path,
                      "auth": auth_output_path, "ui": ui_output_path}
        self.run_frontend_build = env_flag("FORGE_QA_FRONTEND_BUILD", True) if run_frontend_build is None else run_frontend_build
        self.pm_data: Optional[PMOutput] = None
        self.ui_data: Optional[UIOutput] = None
        self.backend_data: Optional[BackendOutput] = None
        self.generation_mode = "execution"

    def load_inputs(self) -> None:
        self.pm_data = self.load_upstream("pm", PMOutput, self.paths["pm"])
        self.ui_data = self.load_upstream("ui", UIOutput, self.paths["ui"])
        self.backend_data = self.load_upstream("backend", BackendOutput, self.paths["backend"])
        self.load_upstream("db", DBOutput, self.paths["db"])
        self.load_upstream("auth", AuthOutput, self.paths["auth"])
        if self.project is None:
            raise GenerationError("QA requires the generated project files; refusing to report results without executing tests")

    # ------------------------------------------------------------------ helpers
    def _env(self, tmp: Path) -> Dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GOOGLE_", "GEMINI_")) and k != "USE_LLM"}
        env.update({
            "DATABASE_URL": "sqlite:///" + (tmp / "qa_probe.db").as_posix(),
            "SECRET_KEY": "qa-probe-key",
            "PASSWORD_HASH_ITERATIONS": "1000",
            "FRONTEND_DIST": str(tmp / "none"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        env.pop("ADMIN_EMAIL", None)
        env.pop("ADMIN_PASSWORD", None)
        return env

    def _python(self, code: str, cwd: Path, env: Dict[str, str], timeout: int = 120) -> Tuple[int, str]:
        try:
            proc = subprocess.run([sys.executable, "-c", code], cwd=str(cwd), env=env, capture_output=True,
                                  text=True, timeout=timeout, creationflags=NO_WINDOW)
            return proc.returncode, (proc.stdout + proc.stderr)
        except subprocess.TimeoutExpired:
            return 1, f"Timed out after {timeout}s"

    def _add(self, checks, name, category, status, started, details=""):
        checks.append({"name": name, "category": category, "status": status,
                       "duration_ms": round((time.monotonic() - started) * 1000, 1), "details": details[-3000:]})
        icon = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}[status]
        self.log(f"[{icon}] {name}" + (f" - {details.splitlines()[0][:160]}" if details and status != "passed" else ""),
                 "warning" if status == "failed" else "info")

    # ------------------------------------------------------------------ checks
    def _check_syntax(self, backend_dir: Path) -> List[str]:
        problems = []
        for path in sorted(backend_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
            except SyntaxError as exc:
                problems.append(f"{path.relative_to(backend_dir).as_posix()}:{exc.lineno}: {exc.msg}")
        return problems

    def _run_pytest(self, backend_dir: Path, tmp: Path) -> Tuple[int, str, List[Dict[str, Any]]]:
        junit = tmp / "junit.xml"
        env = self._env(tmp)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}", "-W", "ignore"],
                cwd=str(backend_dir), env=env, capture_output=True, text=True, timeout=900, creationflags=NO_WINDOW,
            )
            output = proc.stdout + proc.stderr
            code = proc.returncode
        except subprocess.TimeoutExpired:
            return 1, "pytest timed out after 900s", []
        results = []
        if junit.is_file():
            for case in ET.parse(junit).getroot().iter("testcase"):
                suite = (case.get("classname") or "").split(".")[-1]
                status, message = "passed", None
                for tag in ("failure", "error", "skipped"):
                    node = case.find(tag)
                    if node is not None:
                        status = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
                        message = ((node.get("message") or "") + "\n" + (node.text or "")).strip()[-1500:]
                        break
                results.append({"suite": suite, "name": case.get("name"), "status": status,
                                "duration_ms": round(float(case.get("time") or 0) * 1000, 1), "message": message})
        return code, output, results

    def _check_frontend_imports(self, frontend_dir: Path) -> List[str]:
        problems = []
        pattern = re.compile(r"""(?:from|import)\s+['"](\.{1,2}/[^'"]+)['"]""")
        for path in sorted((frontend_dir / "src").rglob("*")):
            if path.suffix not in (".js", ".jsx"):
                continue
            for match in pattern.finditer(path.read_text(encoding="utf-8")):
                target = (path.parent / match.group(1)).resolve()
                if not target.exists():
                    problems.append(f"{path.relative_to(frontend_dir).as_posix()} imports missing {match.group(1)}")
        return problems

    # ------------------------------------------------------------------ main
    def generate(self) -> Dict[str, Any]:
        bp = build_blueprint(self.pm_data)
        root = self.project.root
        backend_dir, frontend_dir = root / "backend", root / "frontend"
        test_files = write_test_files(bp, self.project)
        self.log(f"Generated {len(test_files)} test files covering {len(bp.entities)} resources, {len(bp.workflows)} workflows, "
                 f"{len(bp.rules)} business rules, {len(bp.metrics)} dashboard metrics, auth and admin")

        checks: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        tests: List[Dict[str, Any]] = []
        frontend_build = "skipped"
        coverage: Dict[str, Any] = {"items": [], "correction_tasks": [], "unsupported": [], "summary": ""}

        def error(category: str, component: str, message: str, test_name: Optional[str] = None):
            classification = FailureClassifier.classify(message)
            agent = AGENT_FOR_COMPONENT.get(component, classification.agent_class)
            errors.append({
                "id": f"QA-{len(errors) + 1:03d}", "type": category, "severity": FailureClassifier.get_severity(category),
                "component": component, "agent": agent, "message": message[:1500],
                "suggestion": FailureClassifier.get_suggestion(category), "test_name": test_name,
            })

        with tempfile.TemporaryDirectory(prefix="forge_qa_") as tmp_name:
            tmp = Path(tmp_name)
            env = self._env(tmp)

            started = time.monotonic()
            syntax = self._check_syntax(backend_dir)
            self._add(checks, "Python syntax (backend)", "static", "failed" if syntax else "passed", started, "\n".join(syntax))
            for p in syntax:
                error("SyntaxError", "backend", p)

            started = time.monotonic()
            code, out = self._python(ROUTES_SCRIPT, backend_dir, env)
            routes: List[Tuple[str, str]] = []
            m = re.search(r"FORGE_ROUTES=(.*)", out)
            if code == 0 and m:
                routes = [tuple(r) for r in json.loads(m.group(1))]
                self._add(checks, "Application import & route registration", "backend", "passed", started,
                          f"{len(routes)} routes registered")
            else:
                self._add(checks, "Application import & route registration", "backend", "failed", started, out)
                error("ImportError", "backend", out.strip()[-1200:] or "Application failed to import")

            started = time.monotonic()
            if routes:
                registered = {(meth, re.sub(r"\{[^}]+\}", "{id}", path)) for meth, path in routes}
                # workflow steps are served by one parameterised route: /actions/{action}
                needed = {(r.method.upper(), re.sub(r"/actions/[\w-]+$", "/actions/{id}", re.sub(r"\{[^}]+\}", "{id}", r.endpoint)))
                          for r in self.ui_data.api_requirements}
                missing = sorted(f"{a} {b}" for a, b in needed - registered)
                self._add(checks, "UI/API contract (frontend calls exist in backend)", "integration",
                          "failed" if missing else "passed", started,
                          ("Missing: " + ", ".join(missing)) if missing else f"{len(needed)} UI API calls matched")
                for item in missing:
                    error("IntegrationError", "integration", f"Frontend calls {item}, which the backend does not expose")
            else:
                self._add(checks, "UI/API contract (frontend calls exist in backend)", "integration", "skipped", started,
                          "Backend did not import")

            started = time.monotonic()
            coverage = check_requirement_coverage(self.pm_data, root, routes or None)
            gaps = [i for i in coverage["items"] if i["status"] == "missing"]
            self._add(checks, "Requirement coverage (prompt specification vs generated app)", "integration",
                      "failed" if gaps else "passed", started,
                      coverage["summary"] + ("\nMissing: " + "; ".join(f"{g['requirement']} ({g['issue']})" for g in gaps[:20])
                                             if gaps else ""))
            for g in gaps:
                component = {"UIAgent": "frontend", "DBAgent": "database", "AuthAgent": "auth",
                             "QAAgent": "qa"}.get(g["agent"], "backend")
                error("IntegrationError", component, f"Requirement not implemented: {g['requirement']} - {g['issue']}")

            started = time.monotonic()
            code, out = self._python(DDL_SCRIPT, backend_dir, env)
            m = re.search(r"FORGE_DDL_OK=(\d+)", out)
            if code == 0 and m:
                self._add(checks, "PostgreSQL DDL compilation", "database", "passed", started, f"{m.group(1)} tables compiled")
            else:
                self._add(checks, "PostgreSQL DDL compilation", "database", "failed", started, out)
                error("DatabaseError", "database", out.strip()[-1200:])

            started = time.monotonic()
            code, out, tests = self._run_pytest(backend_dir, tmp)
            failed_tests = [t for t in tests if t["status"] in ("failed", "error")]
            if tests and not failed_tests and code == 0:
                self._add(checks, "Generated API test suite (pytest)", "backend", "passed", started,
                          f"{len(tests)} tests passed")
            else:
                detail = f"{len(failed_tests)} of {len(tests)} tests failed" if tests else out[-2000:]
                self._add(checks, "Generated API test suite (pytest)", "backend", "failed", started, detail)
                if not tests:
                    error("IntegrationError", "backend", "pytest did not produce results: " + out[-1000:])
                for t in failed_tests:
                    component = "auth" if t["suite"] == "test_auth" else "backend"
                    category = "AuthenticationError" if component == "auth" else "APIError"
                    error(category, component, f"{t['suite']}::{t['name']}: {t['message'] or ''}", test_name=t["name"])

        started = time.monotonic()
        problems = self._check_frontend_imports(frontend_dir)
        self._add(checks, "Frontend module imports resolve", "frontend", "failed" if problems else "passed", started,
                  "\n".join(problems) or "All relative imports resolve")
        for p in problems:
            error("BuildError", "frontend", p)

        started = time.monotonic()
        if not self.run_frontend_build:
            self._add(checks, "Frontend production build (vite)", "frontend", "skipped", started, "Disabled by configuration")
        else:
            from backend.services import toolchain

            ready, message = toolchain.ensure_toolchain(log=self.log)
            if not ready:
                self._add(checks, "Frontend production build (vite)", "frontend", "skipped", started, message)
            else:
                ok, output = toolchain.build_frontend(frontend_dir)
                frontend_build = "passed" if ok else "failed"
                self._add(checks, "Frontend production build (vite)", "frontend", frontend_build, started,
                          "Built frontend/dist" if ok else output)
                if not ok:
                    error("BuildError", "frontend", output[-1200:])

        suites: Dict[str, Dict[str, Any]] = {}
        for t in tests:
            s = suites.setdefault(t["suite"], {"name": t["suite"], "test_type": "integration", "tests_count": 0,
                                               "passed_count": 0, "failed_count": 0})
            s["tests_count"] += 1
            s["passed_count" if t["status"] == "passed" else "failed_count"] += 1 if t["status"] != "skipped" else 0

        passed_tests = sum(1 for t in tests if t["status"] == "passed")
        failed_checks = [c for c in checks if c["status"] == "failed"]
        executed = [c for c in checks if c["status"] != "skipped"]
        units_total = len(tests) + len(executed)
        units_passed = passed_tests + sum(1 for c in executed if c["status"] == "passed")
        status = "failed" if failed_checks else "passed"
        critical = sum(1 for e in errors if e["severity"] == "CRITICAL")
        report: Dict[str, Any] = {
            "project_name": bp.project_name,
            "status": status,
            "tests_run": len(tests),
            "tests_passed": passed_tests,
            "tests_failed": len(tests) - passed_tests - sum(1 for t in tests if t["status"] == "skipped"),
            "errors": errors,
            "critical_errors": critical,
            "warnings": len(errors) - critical,
            "score": round(100.0 * units_passed / units_total, 1) if units_total else 0.0,
            "deployment_ready": status == "passed",
            "affected_component": errors[0]["component"] if errors else None,
            "fix_required": status != "passed",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
            "test_suites": list(suites.values()),
            "test_results": tests,
            "frontend_build": frontend_build,
            "generated_test_files": test_files,
            "requirement_coverage": coverage["items"],
            "correction_tasks": coverage["correction_tasks"],
            "unsupported_requests": coverage["unsupported"],
        }
        healing = SelfHealingManager(max_attempts=1).evaluate(report)
        report["repair_recommendation"] = (healing.repair_request.summary if healing.repair_request else healing.message)
        report["next_step"] = "Proceed to deployment" if status == "passed" else f"Fix required: {report['repair_recommendation']}"
        skipped = [c["name"] for c in checks if c["status"] == "skipped"]
        report["summary"] = (
            f"{passed_tests}/{len(tests)} generated tests passed; {len(executed) - len(failed_checks)}/{len(executed)} checks passed"
            + (f"; {coverage['summary']}" if coverage.get("summary") else "")
            + (f"; skipped: {', '.join(skipped)}" if skipped else "")
        )
        self.log(f"QA {status.upper()}: {report['summary']}", "info" if status == "passed" else "warning")
        return report

    def emit_code(self, output: QAOutput) -> List[str]:
        return list(output.generated_test_files)

    @staticmethod
    def is_success(output: QAOutput) -> bool:
        return output.status == "passed"
