"""UIAgent: Responsible for converting PM output specs into UIOutput schemas."""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from backend.schemas.ui_schema import (
    UIOutput,
    UIPage,
    UIComponent,
    UIRoute,
    UILayout,
    UIForm,
    FrontendDependency,
    APIRequirement,
    StylingRequirements,
)
from backend.exceptions import MissingInputError, ValidationError, GenerationError

logger = logging.getLogger(__name__)


class UIAgent:
    """Agent that translates PM requirements into structured UIOutput specifications."""

    def __init__(
        self,
        pm_output_path: str = "outputs/pm_output.json",
        output_filepath: str = "outputs/ui_output.json"
    ):
        self.pm_output_path = Path(pm_output_path)
        self.output_filepath = Path(output_filepath)

    def get_gemini_model(self):
        """Configure and return Gemini model if LLM usage is enabled."""
        import os
        import google.generativeai as genai

        if os.getenv("USE_LLM", "false").lower() != "true":
            return None

        api_key = os.getenv("GOOGLE_API_KEY")

        if not api_key or api_key == "your_gemini_api_key_here":
            logger.warning(
                "GOOGLE_API_KEY not configured. "
                "Falling back to rule-based UI generator."
            )
            return None

        try:
            genai.configure(api_key=api_key)
            return genai.GenerativeModel("gemini-2.0-flash")
        except Exception as e:
            logger.warning(f"Failed to configure Gemini model: {e}")
            return None

    def run(self) -> UIOutput:
        """Executes the UI specification generation process."""

        # 1. Validate PM input file presence
        if not self.pm_output_path.exists():
            raise MissingInputError(
                f"PM output file not found at path: {self.pm_output_path}"
            )

        # 2. Read file content
        content = self.pm_output_path.read_text(encoding="utf-8").strip()

        if not content:
            raise ValidationError(
                f"PM output file at {self.pm_output_path} is empty."
            )

        # 3. Parse JSON syntax
        try:
            pm_data = json.loads(content)
        except Exception as e:
            raise ValidationError(
                f"Failed to parse JSON in PM output file "
                f"{self.pm_output_path}: {e}"
            )

        # 4. Validate mandatory schema fields
        if (
            not isinstance(pm_data, dict)
            or "project_name" not in pm_data
            or not pm_data["project_name"]
        ):
            raise ValidationError(
                "PM output specification must be a dictionary "
                "containing a non-empty 'project_name'."
            )

        # 5. Attempt generation with Gemini LLM,
        #    fallback to dynamic rule-based generator on failure
        ui_output: Optional[UIOutput] = None

        try:
            model = self.get_gemini_model()

            # If LLM is disabled/not configured, directly use fallback
            if model is not None:
                prompt = f"""
                You are a senior UI/UX engineer. Analyze the following
                Product Manager specification and produce a complete JSON
                output matching the UIOutput schema.

                PM Spec:
                {json.dumps(pm_data, indent=2)}
                """

                response = model.generate_content(prompt)

                if hasattr(response, "text") and response.text:
                    # Extract JSON from codeblocks if present
                    raw_text = response.text.strip()

                    if "```json" in raw_text:
                        raw_text = (
                            raw_text
                            .split("```json")[1]
                            .split("```")[0]
                            .strip()
                        )
                    elif "```" in raw_text:
                        raw_text = (
                            raw_text
                            .split("```")[1]
                            .split("```")[0]
                            .strip()
                        )

                    parsed_llm = json.loads(raw_text)
                    ui_output = UIOutput(**parsed_llm)

        except Exception as exc:
            logger.warning(
                "Gemini LLM generation failed or was bypassed. "
                f"Falling back to rule-based generator: {exc}"
            )
            ui_output = self._generate_fallback_ui_output(pm_data)

        if ui_output is None:
            ui_output = self._generate_fallback_ui_output(pm_data)

        # 6. Save output JSON to disk
        self.output_filepath.parent.mkdir(parents=True, exist_ok=True)

        self.output_filepath.write_text(
            ui_output.model_dump_json(indent=2),
            encoding="utf-8"
        )

        return ui_output

    def _generate_fallback_ui_output(
        self,
        pm_data: Dict[str, Any]
    ) -> UIOutput:
        """Derives a complete, schema-compliant UI specification dynamically from arbitrary PM data."""

        project_name = pm_data.get("project_name", "App")
        entities = pm_data.get("database_entities", [])

        pages = [
            UIPage(
                name="DashboardPage",
                route_path="/",
                layout="MainLayout",
                description=f"Main dashboard summary overview for {project_name}",
                components_used=[
                    "Navbar",
                    "Sidebar",
                    "StatsCard"
                ],
                required_auth=True,
                state_requirements=[
                    "currentUser",
                    "metrics"
                ],
            ),
            UIPage(
                name="LoginPage",
                route_path="/login",
                layout="AuthLayout",
                description="User authentication login page",
                components_used=[
                    "LoginForm",
                    "AuthCard"
                ],
                required_auth=False,
                state_requirements=[
                    "loginCredentials",
                    "authError"
                ],
            ),
            UIPage(
                name="RegisterPage",
                route_path="/register",
                layout="AuthLayout",
                description="User account registration page",
                components_used=[
                    "RegisterForm",
                    "AuthCard"
                ],
                required_auth=False,
                state_requirements=[
                    "registrationData",
                    "validationErrors"
                ],
            ),
        ]

        routes = [
            UIRoute(
                path="/",
                component_name="DashboardPage",
                exact=True,
                protected=True,
                title=f"{project_name} - Dashboard"
            ),
            UIRoute(
                path="/login",
                component_name="LoginPage",
                exact=True,
                protected=False,
                title=f"{project_name} - Login"
            ),
            UIRoute(
                path="/register",
                component_name="RegisterPage",
                exact=True,
                protected=False,
                title=f"{project_name} - Register"
            ),
        ]

        components = [
            UIComponent(
                name="Navbar",
                type="navbar",
                description="Top navigation header",
                props=[
                    {
                        "name": "user",
                        "type": "UserObject",
                        "required": "false"
                    },
                    {
                        "name": "onLogout",
                        "type": "function",
                        "required": "false"
                    }
                ],
                state_variables=[
                    {
                        "name": "isProfileDropdownOpen",
                        "type": "boolean",
                        "default": "false"
                    }
                ],
                event_handlers=[
                    "onToggleMenu",
                    "onLogoutClick"
                ],
                child_components=[
                    "UserProfileDropdown",
                    "ThemeToggle"
                ],
            ),
            UIComponent(
                name="Sidebar",
                type="sidebar",
                description="Collapsible side navigation bar",
                props=[
                    {
                        "name": "activePath",
                        "type": "string",
                        "required": "true"
                    }
                ],
                state_variables=[
                    {
                        "name": "isCollapsed",
                        "type": "boolean",
                        "default": "false"
                    }
                ],
                event_handlers=[
                    "onNavigate"
                ],
                child_components=[],
            ),
            UIComponent(
                name="StatsCard",
                type="card",
                description="Visual metric card",
                props=[
                    {
                        "name": "title",
                        "type": "string",
                        "required": "true"
                    },
                    {
                        "name": "value",
                        "type": "number",
                        "required": "true"
                    }
                ],
                state_variables=[],
                event_handlers=[],
                child_components=[],
            ),
            UIComponent(
                name="AuthCard",
                type="card",
                description="Container card for authentication pages",
                props=[],
                state_variables=[],
                event_handlers=[],
                child_components=[],
            ),
            UIComponent(
                name="LoginForm",
                type="form",
                description="User login form",
                props=[],
                state_variables=[],
                event_handlers=[
                    "onSubmit"
                ],
                child_components=[],
            ),
            UIComponent(
                name="RegisterForm",
                type="form",
                description="User registration form",
                props=[],
                state_variables=[],
                event_handlers=[
                    "onSubmit"
                ],
                child_components=[],
            ),
        ]

        forms = [
            UIForm(
                name="LoginForm",
                entity_name="User",
                fields=[
                    {
                        "name": "email",
                        "type": "VARCHAR"
                    },
                    {
                        "name": "password",
                        "type": "VARCHAR"
                    }
                ],
                submit_endpoint="/api/auth/login",
            ),
            UIForm(
                name="RegisterForm",
                entity_name="User",
                fields=[
                    {
                        "name": "email",
                        "type": "VARCHAR"
                    },
                    {
                        "name": "password",
                        "type": "VARCHAR"
                    }
                ],
                submit_endpoint="/api/auth/register",
            ),
        ]

        api_requirements = [
            APIRequirement(
                endpoint="/api/auth/login",
                method="POST",
                description="User authentication endpoint"
            ),
            APIRequirement(
                endpoint="/api/auth/register",
                method="POST",
                description="User registration endpoint"
            ),
        ]

        # Dynamically process entities from pm_data
        for entity in entities:
            entity_name = entity.get("name", "Item")
            cap_entity = entity_name.capitalize()
            entity_lower = entity_name.lower()

            # Correct pluralization
            if entity_lower.endswith("y"):
                lower_plural = entity_lower[:-1] + "ies"
            else:
                lower_plural = entity_lower + "s"

            # Dynamic Page
            pages.append(
                UIPage(
                    name=f"{cap_entity}Page",
                    route_path=f"/{lower_plural}",
                    layout="MainLayout",
                    description=f"Management page for {cap_entity} items",
                    components_used=[
                        "Navbar",
                        "Sidebar",
                        f"{cap_entity}Table",
                        f"{cap_entity}FilterBar"
                    ],
                    required_auth=True,
                    state_requirements=[
                        f"{lower_plural}List",
                        "filterQuery"
                    ],
                )
            )

            pages.append(
                UIPage(
                    name=f"{cap_entity}DetailPage",
                    route_path=f"/{lower_plural}/:id",
                    layout="MainLayout",
                    description=f"Detailed view and editor for {cap_entity}",
                    components_used=[
                        "Navbar",
                        "Sidebar",
                        f"{cap_entity}Detail",
                        f"{cap_entity}Form"
                    ],
                    required_auth=True,
                    state_requirements=[
                        f"selected{cap_entity}",
                        "isEditing"
                    ],
                )
            )

            # Dynamic Routes
            routes.append(
                UIRoute(
                    path=f"/{lower_plural}",
                    component_name=f"{cap_entity}Page",
                    exact=True,
                    protected=True,
                    title=f"{project_name} - {cap_entity}s"
                )
            )

            routes.append(
                UIRoute(
                    path=f"/{lower_plural}/:id",
                    component_name=f"{cap_entity}DetailPage",
                    exact=True,
                    protected=True,
                    title=f"{project_name} - {cap_entity} Detail"
                )
            )

            # Dynamic Components
            components.append(
                UIComponent(
                    name=f"{cap_entity}Table",
                    type="table",
                    description=f"Tabular list of {cap_entity} entries",
                    props=[
                        {
                            "name": "items",
                            "type": "Array",
                            "required": "true"
                        }
                    ],
                    state_variables=[
                        {
                            "name": "sortColumn",
                            "type": "string",
                            "default": "'id'"
                        }
                    ],
                    event_handlers=[
                        "handleSort",
                        "handleSelectRow"
                    ],
                    child_components=[],
                )
            )

            components.append(
                UIComponent(
                    name=f"{cap_entity}Form",
                    type="form",
                    description=f"Form for creating/editing {cap_entity}",
                    props=[
                        {
                            "name": "initialValues",
                            "type": "Object",
                            "required": "false"
                        }
                    ],
                    state_variables=[],
                    event_handlers=[
                        "handleSubmit"
                    ],
                    child_components=[],
                )
            )

            components.append(
                UIComponent(
                    name=f"{cap_entity}Detail",
                    type="card",
                    description=f"Detail viewer component for {cap_entity}",
                    props=[
                        {
                            "name": "item",
                            "type": "Object",
                            "required": "true"
                        }
                    ],
                    state_variables=[],
                    event_handlers=[],
                    child_components=[],
                )
            )

            components.append(
                UIComponent(
                    name=f"{cap_entity}FilterBar",
                    type="filter",
                    description=f"Filter bar for {cap_entity} entries",
                    props=[
                        {
                            "name": "onFilter",
                            "type": "function",
                            "required": "true"
                        }
                    ],
                    state_variables=[],
                    event_handlers=[
                        "onFilterChange"
                    ],
                    child_components=[],
                )
            )

            # Dynamic Form
            fields = entity.get("fields", [])

            forms.append(
                UIForm(
                    name=f"{cap_entity}Form",
                    entity_name=cap_entity,
                    fields=fields,
                    submit_endpoint=f"/api/{lower_plural}",
                )
            )

            # Dynamic API requirements
            api_requirements.extend(
                [
                    APIRequirement(
                        endpoint=f"/api/{lower_plural}",
                        method="GET",
                        description=f"Fetch list of {cap_entity} records"
                    ),
                    APIRequirement(
                        endpoint=f"/api/{lower_plural}",
                        method="POST",
                        description=f"Create a new {cap_entity} record"
                    ),
                    APIRequirement(
                        endpoint=f"/api/{lower_plural}/:id",
                        method="PUT",
                        description=f"Update a {cap_entity} record"
                    ),
                    APIRequirement(
                        endpoint=f"/api/{lower_plural}/:id",
                        method="DELETE",
                        description=f"Delete a {cap_entity} record"
                    ),
                ]
            )

        frontend_dependencies = [
            FrontendDependency(
                package_name="react",
                version="^18.2.0",
                purpose="Core React framework",
                category="core"
            ),
            FrontendDependency(
                package_name="react-dom",
                version="^18.2.0",
                purpose="React DOM renderer",
                category="core"
            ),
            FrontendDependency(
                package_name="react-router-dom",
                version="^6.20.0",
                purpose="Client-side routing",
                category="routing"
            ),
            FrontendDependency(
                package_name="axios",
                version="^1.6.2",
                purpose="HTTP client for API integration",
                category="http"
            ),
            FrontendDependency(
                package_name="lucide-react",
                version="^0.294.0",
                purpose="Icon library",
                category="icons"
            ),
        ]

        layouts = [
            UILayout(
                name="MainLayout",
                description="Standard main application layout",
                slots=["main"],
                default_layout=True
            ),
            UILayout(
                name="AuthLayout",
                description="Authentication page layout",
                slots=["main"],
                default_layout=False
            ),
        ]

        styling_requirements = StylingRequirements(
            theme_mode="dark",
            primary_color="#6366F1",
            font_family="Inter, sans-serif",
            design_system_notes="Modern dark theme UI with sleek gradients",
            css_approach="Vanilla CSS",
        )

        return UIOutput(
            project_name=project_name,
            pages=pages,
            components=components,
            routes=routes,
            layouts=layouts,
            forms=forms,
            frontend_dependencies=frontend_dependencies,
            api_requirements=api_requirements,
            styling_requirements=styling_requirements,
        )