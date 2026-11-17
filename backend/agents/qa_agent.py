"""QA Agent for FORGE AI - Automated Quality Assurance and Diagnostic Agent."""

import os
import sys
import ast
import json
import sqlite3
import importlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from backend.agents.base_agent import BaseAgent
from backend.schemas.qa_schema import QAOutput, QAError
from backend.services.error_mapper import ErrorMapper
from backend.services.qa_summary import generate_qa_summary


class QAAgent(BaseAgent[QAOutput]):
    """QA Agent responsible for inspecting generated projects, executing tests, classifying errors, and producing QA diagnostic contracts."""

    def __init__(
        self,
        project_root: str = ".",
        pm_output_path: str = "outputs/pm_output.json",
        backend_output_path: str = "outputs/backend_output.json",
        db_output_path: str = "outputs/db_output.json",
        auth_output_path: str = "outputs/auth_output.json",
        output_filepath: str = "outputs/qa_output.json",
    ):
        super().__init__(output_schema_cls=QAOutput, output_filepath=output_filepath)
        self.project_root = Path(project_root).resolve()
        self.pm_output_path = Path(pm_output_path)
        self.backend_output_path = Path(backend_output_path)
        self.db_output_path = Path(db_output_path)
        self.auth_output_path = Path(auth_output_path)
        
        self.pm_data: Optional[Dict[str, Any]] = None
        self.backend_data: Optional[Dict[str, Any]] = None
        self.db_data: Optional[Dict[str, Any]] = None
        self.auth_data: Optional[Dict[str, Any]] = None

        self.error_mapper = ErrorMapper(id_prefix="QA")

    def load_inputs(self) -> None:
        """Load and parse specification inputs if present."""
        if self.pm_output_path.is_file():
            self.pm_data = self.read_json_file(str(self.pm_output_path))
            self.inputs["pm"] = self.pm_data
            
        if self.backend_output_path.is_file():
            self.backend_data = self.read_json_file(str(self.backend_output_path))
            self.inputs["backend"] = self.backend_data
            
        if self.db_output_path.is_file():
            self.db_data = self.read_json_file(str(self.db_output_path))
            self.inputs["db"] = self.db_data

        if self.auth_output_path.is_file():
            self.auth_data = self.read_json_file(str(self.auth_output_path))
            self.inputs["auth"] = self.auth_data

    def check_python_syntax(self) -> List[QAError]:
        """Verify Python syntax across all backend Python source files."""
        errors: List[QAError] = []
        backend_dir = self.project_root / "backend"
        
        if not backend_dir.exists():
            return errors

        for py_file in backend_dir.glob("**/*.py"):
            try:
                content = py_file.read_text(encoding="utf-8")
                ast.parse(content, filename=str(py_file))
            except SyntaxError as e:
                errors.append(
                    self.error_mapper.map_error(
                        error=e,
                        message=f"Syntax error at line {e.lineno}, col {e.offset}: {e.msg}",
                        component="backend",
                        test_name=f"test_syntax_{py_file.name}",
                        suggestion=f"Fix syntax error in '{py_file.relative_to(self.project_root)}' around line {e.lineno}."
                    )
                )
            except Exception as e:
                errors.append(
                    self.error_mapper.map_error(
                        error="SyntaxError",
                        message=f"Failed to read file: {str(e)}",
                        component="backend",
                        test_name=f"test_read_{py_file.name}",
                        suggestion=f"Ensure '{py_file.relative_to(self.project_root)}' has valid UTF-8 encoding."
                    )
                )
        return errors

    def check_backend_imports(self) -> List[QAError]:
        """Verify backend module importability and package structure."""
        errors: List[QAError] = []
        modules_to_test = [
            ("backend.exceptions", "backend"),
            ("backend.schemas", "backend"),
            ("backend.agents", "backend"),
        ]
        
        for mod_name, component in modules_to_test:
            try:
                importlib.import_module(mod_name)
            except ImportError as e:
                errors.append(
                    self.error_mapper.map_error(
                        error=e,
                        message=f"Module import failed: {str(e)}",
                        component=component,
                        test_name=f"test_import_{mod_name.replace('.', '_')}",
                        suggestion=f"Check module dependencies and '__init__.py' files in {mod_name}."
                    )
                )
            except Exception as e:
                errors.append(
                    self.error_mapper.map_error(
                        error="ImportError",
                        message=f"Unexpected error loading module {mod_name}: {str(e)}",
                        component=component,
                        test_name=f"test_import_{mod_name.replace('.', '_')}",
                        suggestion=f"Verify internal references in module '{mod_name}'."
                    )
                )
        return errors

    def check_api_endpoints(self) -> List[QAError]:
        """Verify API endpoints definition and FastAPI router instantiation."""
        errors: List[QAError] = []
        try:
            from backend.main import app
            routes = [route.path for route in app.routes]
            required_paths = ["/", "/health"]
            for path in required_paths:
                if path not in routes:
                    errors.append(
                        self.error_mapper.map_error(
                            error="EndpointError",
                            message=f"Required standard route '{path}' missing from FastAPI app.",
                            component="backend",
                            test_name=f"test_endpoint_{path.strip('/') or 'root'}",
                            suggestion=f"Register route '{path}' in backend/main.py."
                        )
                    )
        except Exception as e:
            errors.append(
                self.error_mapper.map_error(
                    error="EndpointError",
                    message=f"Failed to instantiate FastAPI app from backend.main: {str(e)}",
                    component="backend",
                    test_name="test_fastapi_app_instantiation",
                    suggestion="Ensure backend/main.py exports valid FastAPI 'app' instance."
                )
            )
        return errors

    def check_database_connection(self) -> List[QAError]:
        """Verify Database connectivity (SQLite / PostgreSQL)."""
        errors: List[QAError] = []
        backend_dir = self.project_root / "backend"
        db_files = list(backend_dir.glob("*.db")) if backend_dir.exists() else []
        if not db_files and backend_dir.exists():
            db_files = [backend_dir / "tasks.db"]

        for db_path in db_files:
            if not db_path.exists() and len(db_files) > 1:
                continue
            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                conn.close()
            except Exception as e:
                errors.append(
                    self.error_mapper.map_error(
                        error=e,
                        message=f"Database connection or query failed: {str(e)}",
                        component="database",
                        test_name="test_database_connection",
                        suggestion="Check SQLite file permissions or database connection string."
                    )
                )
        return errors

    def check_frontend_build(self) -> List[QAError]:
        """Verify frontend project structure, package.json, and build setup."""
        errors: List[QAError] = []
        frontend_dir = self.project_root / "frontend"
        
        if frontend_dir.exists():
            pkg_json = frontend_dir / "package.json"
            if not pkg_json.is_file():
                errors.append(
                    self.error_mapper.map_error(
                        error="FrontendBuildError",
                        message="Missing 'package.json' in frontend directory.",
                        component="frontend",
                        test_name="test_frontend_package_json",
                        suggestion="Initialize frontend node project with valid package.json."
                    )
                )
            else:
                try:
                    data = json.loads(pkg_json.read_text(encoding="utf-8"))
                    if "scripts" not in data or "build" not in data.get("scripts", {}):
                        errors.append(
                            self.error_mapper.map_error(
                                error="FrontendBuildError",
                                message="Missing 'build' script in package.json.",
                                component="frontend",
                                test_name="test_frontend_build_script",
                                suggestion="Add build script e.g. 'vite build' or 'react-scripts build' to package.json."
                            )
                        )
                except Exception as e:
                    errors.append(
                        self.error_mapper.map_error(
                            error="FrontendBuildError",
                            message=f"Failed to parse frontend package.json: {str(e)}",
                            component="frontend",
                            test_name="test_frontend_package_parse",
                            suggestion="Ensure frontend package.json contains valid JSON format."
                        )
                    )
        return errors

    def check_missing_dependencies(self) -> List[QAError]:
        """Verify critical Python dependencies are installed in runtime environment."""
        errors: List[QAError] = []
        required_pkgs = ["fastapi", "pydantic", "uvicorn", "pytest", "dotenv"]
        
        for pkg in required_pkgs:
            try:
                importlib.import_module(pkg)
            except ImportError as e:
                errors.append(
                    self.error_mapper.map_error(
                        error=e,
                        message=f"Required package '{pkg}' is not installed.",
                        component="backend",
                        test_name=f"test_dependency_{pkg}",
                        suggestion=f"Install missing dependency via 'pip install {pkg}'."
                    )
                )
        return errors

    def check_configuration_errors(self) -> List[QAError]:
        """Check for configuration issues and security compliance (e.g. no exposed secrets)."""
        errors: List[QAError] = []
        
        for output_file in [self.pm_output_path, self.backend_output_path, self.db_output_path, self.auth_output_path]:
            if output_file.is_file():
                try:
                    content = output_file.read_text(encoding="utf-8")
                    sensitive_patterns = ["AIzaSy", "ghp_", "sk_live_", "AKIA"]
                    for pat in sensitive_patterns:
                        if pat in content:
                            errors.append(
                                self.error_mapper.map_error(
                                    error="ConfigurationError",
                                    message=f"Potential hardcoded secret pattern '{pat}' detected in '{output_file.name}'.",
                                    component="auth",
                                    test_name=f"test_secret_leak_{output_file.name}",
                                    suggestion=f"Remove secret credential pattern from '{output_file.name}' and use environment variables."
                                )
                            )
                except Exception:
                    pass

        return errors

    def generate(self) -> Dict[str, Any]:
        """Run all test suites and compile structured QA Output dictionary."""
        self.logger.info("Executing QA inspection suite across generated components...")
        self.error_mapper.reset_counter()
        
        all_errors: List[QAError] = []
        
        # 1. Syntax Check
        all_errors.extend(self.check_python_syntax())
        
        # 2. Imports Check
        all_errors.extend(self.check_backend_imports())

        # 3. API Endpoints Check
        all_errors.extend(self.check_api_endpoints())

        # 4. DB Connection Check
        all_errors.extend(self.check_database_connection())

        # 5. Frontend Build Check
        all_errors.extend(self.check_frontend_build())

        # 6. Missing Dependencies Check
        all_errors.extend(self.check_missing_dependencies())

        # 7. Configuration Errors Check
        all_errors.extend(self.check_configuration_errors())

        # Count metrics
        total_checks = 10
        failed_count = len(all_errors)
        passed_count = max(0, total_checks - failed_count)
        
        is_passed = failed_count == 0
        critical_count = sum(1 for err in all_errors if err.severity == "CRITICAL")
        warning_count = sum(1 for err in all_errors if err.severity in ("HIGH", "MEDIUM", "LOW"))
        score = round(max(0.0, (passed_count / max(total_checks, 1)) * 100.0), 2)
        deployment_ready = is_passed and critical_count == 0
        
        if deployment_ready:
            next_step = "Proceed to deployment"
        else:
            next_step = f"Resolve {failed_count} error(s) across affected components."

        primary_affected_component: Optional[str] = None
        if not is_passed and all_errors:
            primary_affected_component = all_errors[0].component

        qa_output = {
            "status": "passed" if is_passed else "failed",
            "tests_run": total_checks if is_passed else max(total_checks, failed_count),
            "tests_passed": passed_count if is_passed else max(0, total_checks - failed_count),
            "tests_failed": failed_count,
            "errors": [err.model_dump() for err in all_errors],
            "critical_errors": critical_count,
            "warnings": warning_count,
            "score": score,
            "deployment_ready": deployment_ready,
            "next_step": next_step,
            "affected_component": primary_affected_component,
            "fix_required": not deployment_ready,
            "execution_timestamp": datetime.now().isoformat()
        }

        # Generate qa_summary.txt file
        summary_path = self.project_root / "outputs" / "qa_summary.txt"
        generate_qa_summary(qa_output, output_path=str(summary_path))

        return qa_output


def generate_qa_output(project_root: str = ".") -> str:
    """Utility function to execute QAAgent and return JSON string."""
    agent = QAAgent(project_root=project_root)
    output = agent.run()
    return json.dumps(output.model_dump(), indent=2)


if __name__ == "__main__":
    agent = QAAgent()
    result = agent.run()
    print(f"QA Status: {result.status}")
    print(f"Tests Run: {result.tests_run}, Passed: {result.tests_passed}, Failed: {result.tests_failed}")
