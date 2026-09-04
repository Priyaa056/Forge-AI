"""UI Agent for FORGE AI platform."""

import json
from typing import Dict, Any, Optional
from pathlib import Path

from backend.agents.base_agent import BaseAgent
from backend.schemas.pm_schema import PMOutput
from backend.schemas.ui_schema import UIOutput, PageComponentSpec, UIComponentSpec
from backend.schemas.backend_schema import BackendOutput
from backend.artifacts.artifact_context import ArtifactContext
from backend.exceptions import MissingInputError, ValidationError, GenerationError


class UIAgent(BaseAgent[UIOutput]):
    """Agent responsible for generating frontend UI specs and component code from PM/Backend specs."""

    def __init__(
        self,
        pm_output_path: str = "outputs/pm_output.json",
        backend_output_path: Optional[str] = "outputs/backend_output.json",
        output_filepath: str = "outputs/ui_output.json",
        artifact_context: Optional[ArtifactContext] = None,
    ):
        super().__init__(
            output_schema_cls=UIOutput,
            output_filepath=output_filepath,
            artifact_context=artifact_context,
        )
        self.pm_output_path = pm_output_path
        self.backend_output_path = backend_output_path
        self.pm_data: Optional[PMOutput] = None
        self.backend_data: Optional[Dict[str, Any]] = None

    def load_inputs(self) -> None:
        """Load and validate inputs from PM and optional Backend agent."""
        if self.artifact_context:
            self.pm_data = self.artifact_context.get_validated_content("pm", PMOutput)
            backend_out = self.artifact_context.get_validated_content("backend", BackendOutput, optional=True)
            self.backend_data = backend_out.model_dump() if backend_out else None
        else:
            raw_pm = self.read_json_file(self.pm_output_path)
            try:
                self.pm_data = PMOutput.model_validate(raw_pm)
            except Exception as e:
                raise ValidationError(f"Invalid pm_output.json format: {e}")

            if self.backend_output_path and Path(self.backend_output_path).is_file():
                try:
                    self.backend_data = self.read_json_file(self.backend_output_path)
                except Exception as e:
                    self.logger.warning(f"Failed to parse optional backend_output.json: {e}")


    def _generate_rule_based(self) -> Dict[str, Any]:
        """Rule-based fallback generator for UI specs and boilerplate component code."""
        if not self.pm_data:
            raise GenerationError("Inputs not loaded. Call load_inputs() first.")

        project_name = self.pm_data.project_name
        entities = self.pm_data.database_entities

        pages = [
            {
                "name": "Dashboard",
                "path": "/",
                "components": ["Navbar", "Sidebar", "MetricsCard"],
                "description": f"Main dashboard overview for {project_name}"
            },
            {
                "name": "Login",
                "path": "/login",
                "components": ["LoginForm"],
                "description": "User authentication page"
            }
        ]

        components = [
            {
                "name": "Navbar",
                "description": "Top navigation header bar",
                "props": [{"name": "title", "type": "string"}, {"name": "user", "type": "object"}]
            },
            {
                "name": "Sidebar",
                "description": "Navigation side drawer menu",
                "props": [{"name": "activeRoute", "type": "string"}]
            },
            {
                "name": "MetricsCard",
                "description": "Dashboard summary statistics card",
                "props": [{"name": "label", "type": "string"}, {"name": "value", "type": "number"}]
            }
        ]

        routes = [
            {"path": "/", "component": "Dashboard"},
            {"path": "/login", "component": "Login"}
        ]

        code_files = {
            "src/components/Navbar.jsx": (
                "import React from 'react';\n\n"
                "export const Navbar = ({ title }) => (\n"
                "  <header className=\"bg-slate-900 text-white p-4 flex justify-between items-center shadow\">\n"
                f"    <h1 className=\"text-xl font-bold\">{{title || '{project_name}'}}</h1>\n"
                "  </header>\n"
                ");\n"
            ),
            "src/pages/Dashboard.jsx": (
                "import React from 'react';\n"
                "import { Navbar } from '../components/Navbar';\n\n"
                "export const Dashboard = () => (\n"
                "  <div className=\"min-h-screen bg-slate-950 text-slate-100\">\n"
                f"    <Navbar title=\"{project_name} Dashboard\" />\n"
                "    <main className=\"p-6\">\n"
                f"      <h2 className=\"text-2xl font-semibold mb-4\">Welcome to {project_name}</h2>\n"
                "    </main>\n"
                "  </div>\n"
                ");\n"
            )
        }

        # Add entity-specific pages and components dynamically
        for entity in entities:
            entity_name = entity.name.capitalize()
            page_name = f"{entity_name}Manager"
            page_path = f"/{entity_name.lower()}s"

            pages.append({
                "name": page_name,
                "path": page_path,
                "components": [f"{entity_name}Table", f"{entity_name}Form"],
                "description": f"Manage {entity_name} records"
            })

            components.append({
                "name": f"{entity_name}Table",
                "description": f"Data table displaying {entity_name} list",
                "props": [{"name": "data", "type": "array"}]
            })

            routes.append({"path": page_path, "component": page_name})

            code_files[f"src/pages/{page_name}.jsx"] = (
                "import React from 'react';\n\n"
                f"export const {page_name} = () => (\n"
                "  <div className=\"p-6\">\n"
                f"    <h2 className=\"text-xl font-bold\">{entity_name} Management</h2>\n"
                "  </div>\n"
                ");\n"
            )

        return {
            "project_name": project_name,
            "framework": "React",
            "styling": "Tailwind CSS",
            "pages": pages,
            "components": components,
            "design_system": {
                "theme": "dark",
                "primaryColor": "#3b82f6",
                "secondaryColor": "#1e293b",
                "fontFamily": "Inter, sans-serif"
            },
            "routes": routes,
            "code_files": code_files
        }

    def generate(self) -> Dict[str, Any]:
        """Generate UI specification using Gemini LLM or rule-based fallback."""
        if not self.pm_data:
            raise GenerationError("Inputs not loaded. Call load_inputs() first.")

        model = self.get_gemini_model()
        if model:
            try:
                prompt = (
                    f"Generate UI spec JSON for '{self.pm_data.project_name}'. "
                    f"Features: {self.pm_data.features}. Entities: {[e.name for e in self.pm_data.database_entities]}."
                )
                response = model.generate_content(prompt)
                text = response.text.strip()
                if text.startswith("```json"):
                    text = text[7:]
                if text.endswith("```"):
                    text = text[:-3]
                parsed = json.loads(text.strip())
                UIOutput.model_validate(parsed)
                return parsed
            except Exception as e:
                self.logger.warning(f"Gemini LLM UI generation failed: {e}. Using rule-based fallback.")

        return self._generate_rule_based()
