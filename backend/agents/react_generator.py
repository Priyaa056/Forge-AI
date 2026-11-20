"""ReactGenerator: Downstream component responsible for generating React source files from UIOutput."""

import json
import re
from pathlib import Path

from backend.schemas.ui_schema import (
    UIOutput,
    UIComponent,
    UIPage,
    UILayout,
)
from backend.exceptions import (
    MissingInputError,
    ValidationError,
    GenerationError,
)


class ReactGenerator:
    """Consumes UIOutput specification and generates React application source code."""

    def __init__(
        self,
        ui_output_path: str = "outputs/ui_output.json",
        output_dir: str = "frontend",
    ):
        self.ui_output_path = Path(ui_output_path)
        self.output_dir = Path(output_dir)

    def run(self) -> Path:
        """Execute React code generation."""

        # --------------------------------------------------------------
        # 1. Validate UI output path
        # --------------------------------------------------------------
        if not self.ui_output_path.exists():
            raise MissingInputError(
                f"UI output file not found at path: {self.ui_output_path}"
            )

        # --------------------------------------------------------------
        # 2. Read file content
        # --------------------------------------------------------------
        content = self.ui_output_path.read_text(
            encoding="utf-8"
        ).strip()

        if not content:
            raise ValidationError(
                f"UI output file at {self.ui_output_path} is empty."
            )

        # --------------------------------------------------------------
        # 3. Parse JSON
        # --------------------------------------------------------------
        try:
            ui_data = json.loads(content)
        except Exception as e:
            raise ValidationError(
                f"Failed to parse JSON in UI output file "
                f"{self.ui_output_path}: {e}"
            )

        # --------------------------------------------------------------
        # 4. Basic validation
        # --------------------------------------------------------------
        if (
            not isinstance(ui_data, dict)
            or "project_name" not in ui_data
            or "components" not in ui_data
        ):
            raise ValidationError(
                "UI output specification must contain "
                "'project_name' and 'components'."
            )

        # --------------------------------------------------------------
        # 5. Pydantic validation
        # --------------------------------------------------------------
        try:
            ui_spec = UIOutput(**ui_data)
        except Exception as e:
            raise ValidationError(
                f"UI output failed schema validation: {e}"
            )

        try:
            # ----------------------------------------------------------
            # 6. Create directory structure
            # ----------------------------------------------------------
            self.output_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            src_dir = self.output_dir / "src"
            components_dir = src_dir / "components"
            pages_dir = src_dir / "pages"
            layouts_dir = src_dir / "layouts"

            components_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            pages_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            layouts_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            # ----------------------------------------------------------
            # 7. Generate foundation files
            # ----------------------------------------------------------
            self._generate_package_json(ui_spec)
            self._generate_index_html(ui_spec)
            self._generate_vite_config()
            self._generate_main_jsx()
            self._generate_app_jsx(ui_spec)
            self._generate_index_css(ui_spec)

            # ----------------------------------------------------------
            # 8. Generate components
            # ----------------------------------------------------------
            known_component_names = {
                component.name
                for component in ui_spec.components
            }

            for component in ui_spec.components:
                self._generate_component_file(
                    component,
                    components_dir,
                    known_component_names,
                )

            # ----------------------------------------------------------
            # 9. Generate pages
            # ----------------------------------------------------------
            for page in ui_spec.pages:
                self._generate_page_file(
                    page,
                    pages_dir,
                    known_component_names,
                )

            # ----------------------------------------------------------
            # 10. Generate layouts
            # ----------------------------------------------------------
            for layout in ui_spec.layouts:
                self._generate_layout_file(
                    layout,
                    layouts_dir,
                )

            return self.output_dir

        except (
            MissingInputError,
            ValidationError,
            GenerationError,
        ):
            raise

        except Exception as e:
            raise GenerationError(
                f"React application generation failed: {e}"
            )

    # ==================================================================
    # PACKAGE.JSON
    # ==================================================================

    def _generate_package_json(
        self,
        ui_spec: UIOutput,
    ) -> None:
        """Generate package.json with dependencies from UI specification."""

        pkg_name = (
            re.sub(
                r"[^a-z0-9-]",
                "",
                ui_spec.project_name.lower().replace(" ", "-"),
            )
            or "forge-app"
        )

        deps = {}

        for dependency in ui_spec.frontend_dependencies:
            deps[dependency.package_name] = dependency.version

        # Required React dependencies
        if "react" not in deps:
            deps["react"] = "^18.2.0"

        if "react-dom" not in deps:
            deps["react-dom"] = "^18.2.0"

        # React Router is required when routes are generated.
        if (
            ui_spec.routes
            and "react-router-dom" not in deps
        ):
            deps["react-router-dom"] = "^6.22.3"

        pkg_json = {
            "name": pkg_name,
            "private": True,
            "version": "0.1.0",
            "type": "module",
            "scripts": {
                "dev": "vite",
                "build": "vite build",
                "preview": "vite preview",
            },
            "dependencies": deps,
            "devDependencies": {
                "@types/react": "^18.2.37",
                "@types/react-dom": "^18.2.15",
                "@vitejs/plugin-react": "^4.2.0",
                "vite": "^5.0.0",
            },
        }

        (
            self.output_dir / "package.json"
        ).write_text(
            json.dumps(
                pkg_json,
                indent=2,
            ),
            encoding="utf-8",
        )

    # ==================================================================
    # INDEX.HTML
    # ==================================================================

    def _generate_index_html(
        self,
        ui_spec: UIOutput,
    ) -> None:
        """Generate index.html."""

        html_content = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta
      name="viewport"
      content="width=device-width, initial-scale=1.0"
    />
    <title>{ui_spec.project_name}</title>
  </head>
  <body>
    <div id="root"></div>
    <script
      type="module"
      src="/src/main.jsx"
    ></script>
  </body>
</html>
"""

        (
            self.output_dir / "index.html"
        ).write_text(
            html_content,
            encoding="utf-8",
        )

    # ==================================================================
    # VITE CONFIG
    # ==================================================================

    def _generate_vite_config(self) -> None:
        """Generate vite.config.js."""

        code = """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
});
"""

        (
            self.output_dir / "vite.config.js"
        ).write_text(
            code,
            encoding="utf-8",
        )

    # ==================================================================
    # MAIN.JSX
    # ==================================================================

    def _generate_main_jsx(self) -> None:
        """Generate src/main.jsx."""

        code = """import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';

ReactDOM.createRoot(
  document.getElementById('root')
).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
"""

        (
            self.output_dir
            / "src"
            / "main.jsx"
        ).write_text(
            code,
            encoding="utf-8",
        )

    # ==================================================================
    # APP.JSX / ROUTING
    # ==================================================================

    def _generate_app_jsx(
        self,
        ui_spec: UIOutput,
    ) -> None:
        """Generate App.jsx with dynamic React Router routes."""

        if ui_spec.routes:

            lines = [
                "import React from 'react';",
                (
                    "import { BrowserRouter, Routes, Route } "
                    "from 'react-router-dom';"
                ),
                "",
            ]

            imported_components = set()

            for route in ui_spec.routes:

                component_name = route.component_name

                if component_name not in imported_components:

                    lines.append(
                        f"import {component_name} "
                        f"from './pages/{component_name}.jsx';"
                    )

                    imported_components.add(
                        component_name
                    )

            lines.extend(
                [
                    "",
                    "function App() {",
                    "  return (",
                    "    <BrowserRouter>",
                    '      <div className="app-container">',
                    "        <Routes>",
                ]
            )

            for route in ui_spec.routes:

                path = route.path or "/"
                component_name = route.component_name

                lines.append(
                    f'          <Route path="{path}" '
                    f"element={{<{component_name} />}} />"
                )

            lines.extend(
                [
                    "        </Routes>",
                    "      </div>",
                    "    </BrowserRouter>",
                    "  );",
                    "}",
                    "",
                    "export default App;",
                    "",
                ]
            )

            code = "\n".join(lines)

        else:

            code = f"""import React from 'react';

function App() {{
  return (
    <div className="app-container">
      <h1>Welcome to {ui_spec.project_name}</h1>
    </div>
  );
}}

export default App;
"""

        (
            self.output_dir
            / "src"
            / "App.jsx"
        ).write_text(
            code,
            encoding="utf-8",
        )

    # ==================================================================
    # CSS
    # ==================================================================

    def _generate_index_css(
        self,
        ui_spec: UIOutput,
    ) -> None:
        """Generate src/index.css based on styling requirements."""

        styling = ui_spec.styling_requirements

        bg = (
            "#0f172a"
            if styling.theme_mode == "dark"
            else "#ffffff"
        )

        text_color = (
            "#f8fafc"
            if styling.theme_mode == "dark"
            else "#0f172a"
        )

        primary = (
            styling.primary_color
            or "#6366F1"
        )

        font = (
            styling.font_family
            or "Inter, sans-serif"
        )

        css = f"""/* FORGE AI Generated Design System */

:root {{
  --background: {bg};
  --foreground: {text_color};
  --primary: {primary};
  --font-family: {font};
}}

* {{
  box-sizing: border-box;
}}

body {{
  margin: 0;
  padding: 0;
  background-color: var(--background);
  color: var(--foreground);
  font-family: var(--font-family);
}}

.app-container {{
  min-height: 100vh;
  width: 100%;
}}
"""

        (
            self.output_dir
            / "src"
            / "index.css"
        ).write_text(
            css,
            encoding="utf-8",
        )

    # ==================================================================
    # COMPONENT GENERATION
    # ==================================================================

    def _generate_component_file(
        self,
        comp: UIComponent,
        components_dir: Path,
        known_components: set,
    ) -> None:
        """Generate a React component .jsx file."""

        lines = []

        is_stateful = (
            len(comp.state_variables) > 0
        )

        if is_stateful:
            lines.append(
                "import React, { useState } from 'react';"
            )
        else:
            lines.append(
                "import React from 'react';"
            )

        # --------------------------------------------------------------
        # Child component imports
        # --------------------------------------------------------------
        child_placeholders = []

        for child in comp.child_components:

            if child in known_components:

                lines.append(
                    f"import {child} "
                    f"from './{child}.jsx';"
                )

            else:

                child_placeholders.append(
                    f"Child component {child} placeholder"
                )

        lines.append("")

        # --------------------------------------------------------------
        # Props
        # --------------------------------------------------------------
        prop_names = [
            prop.get("name")
            for prop in comp.props
            if isinstance(prop, dict)
            and prop.get("name")
        ]

        if prop_names:

            props_str = ", ".join(
                prop_names
            )

            lines.append(
                f"function {comp.name}"
                f"({{ {props_str} }}) {{"
            )

        else:

            lines.append(
                f"function {comp.name}() {{"
            )

        # --------------------------------------------------------------
        # State variables
        # --------------------------------------------------------------
                # State variables
        for state_variable in comp.state_variables:
            if isinstance(state_variable, dict):
                variable_name = state_variable.get(
                    "name",
                    "stateVar",
                )

                default_value = state_variable.get(
                    "default",
                    "false",
                )

                # Convert JSON/Pydantic string representations
                # into valid JavaScript literals.
                if isinstance(default_value, str):
                    stripped_value = default_value.strip()

                    if stripped_value.lower() == "false":
                        default_value = "false"
                    elif stripped_value.lower() == "true":
                        default_value = "true"
                    elif stripped_value.lower() == "null":
                        default_value = "null"
                    elif (
                        len(stripped_value) >= 2
                        and stripped_value[0] == "'"
                        and stripped_value[-1] == "'"
                    ):
                        # Keep existing JavaScript-style string literals
                        default_value = stripped_value
                    elif (
                        len(stripped_value) >= 2
                        and stripped_value[0] == '"'
                        and stripped_value[-1] == '"'
                    ):
                        # Keep existing JavaScript-style string literals
                        default_value = stripped_value
                    else:
                        # Treat other values as JavaScript expressions/literals.
                        default_value = stripped_value

                elif isinstance(default_value, bool):
                    default_value = "true" if default_value else "false"
                elif default_value is None:
                    default_value = "null"
                else:
                    default_value = str(default_value)

                setter_name = (
                    "set"
                    + variable_name[0].upper()
                    + variable_name[1:]
                )

                lines.append(
                    f"  const [{variable_name}, "
                    f"{setter_name}] = "
                    f"useState({default_value});"
                )

        # --------------------------------------------------------------
        # Event handlers
        # --------------------------------------------------------------
        for handler in comp.event_handlers:

            lines.append(
                f"  const {handler} = (event) => {{"
            )

            lines.append(
                f"    // Handler for {handler}"
            )

            lines.append(
                "  };"
            )

        # --------------------------------------------------------------
        # JSX
        # --------------------------------------------------------------
        lines.append(
            "  return ("
        )

        lines.append(
            f'    <div className="'
            f'{self._to_css_name(comp.name)}-container">'
        )

        lines.append(
            f"      <h3>{comp.name}</h3>"
        )

        for placeholder in child_placeholders:

            lines.append(
                f"      {{/* {placeholder} */}}"
            )

        lines.append(
            "    </div>"
        )

        lines.append(
            "  );"
        )

        lines.append(
            "}"
        )

        lines.append("")

        lines.append(
            f"export default {comp.name};"
        )

        component_file = (
            components_dir
            / f"{comp.name}.jsx"
        )

        component_file.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

    # ==================================================================
    # PAGE GENERATION
    # ==================================================================

    def _generate_page_file(
        self,
        page: UIPage,
        pages_dir: Path,
        known_components: set,
    ) -> None:
        """Generate a React page component from UIPage."""

        lines = [
            "import React from 'react';",
        ]

        # --------------------------------------------------------------
        # Import components used by the page
        # --------------------------------------------------------------
        imported_components = set()

        for component_name in page.components_used:

            if component_name in known_components:

                lines.append(
                    f"import {component_name} "
                    f"from '../components/"
                    f"{component_name}.jsx';"
                )

                imported_components.add(
                    component_name
                )

        lines.append("")

        lines.append(
            f"function {page.name}() {{"
        )

        lines.append(
            "  return ("
        )

        lines.append(
            f'    <div className="'
            f'{self._to_css_name(page.name)}-page">'
        )

        lines.append(
            f"      <h1>{page.name}</h1>"
        )

        # --------------------------------------------------------------
        # Page description
        # --------------------------------------------------------------
        if page.description:

            safe_description = (
                page.description
                .replace("{", "{{")
                .replace("}", "}}")
            )

            lines.append(
                f"      <p>{safe_description}</p>"
            )

        # --------------------------------------------------------------
        # Render components
        # --------------------------------------------------------------
        for component_name in page.components_used:

            if component_name in imported_components:

                lines.append(
                    f"      <{component_name} />"
                )

        # --------------------------------------------------------------
        # Page state requirements
        #
        # IMPORTANT:
        # JSX comments must close with `*/}`
        # --------------------------------------------------------------
        if page.state_requirements:

            lines.append(
                "      {/* Page state requirements:"
            )

            for requirement in page.state_requirements:

                lines.append(
                    f"        - {requirement}"
                )

            # FIX:
            # Previous version generated `*/`
            # instead of `*/}`.
            lines.append(
                "      */}"
            )

        lines.extend(
            [
                "    </div>",
                "  );",
                "}",
                "",
                f"export default {page.name};",
                "",
            ]
        )

        page_file = (
            pages_dir
            / f"{page.name}.jsx"
        )

        page_file.write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

    # ==================================================================
    # LAYOUT GENERATION
    # ==================================================================

    def _generate_layout_file(
        self,
        layout: UILayout,
        layouts_dir: Path,
    ) -> None:
        """Generate a React layout component from UILayout."""

        lines = [
            "import React from 'react';",
            "",
            f"function {layout.name}({{ children }}) {{",
            "  return (",
            f'    <div className="'
            f'{self._to_css_name(layout.name)}-layout">',
        ]

        if layout.description:

            lines.append(
                f"      {{/* {layout.description} */}}"
            )

        lines.extend(
            [
                "      <main>",
                "        {children}",
                "      </main>",
                "    </div>",
                "  );",
                "}",
                "",
                f"export default {layout.name};",
                "",
            ]
        )

        layout_file = (
            layouts_dir
            / f"{layout.name}.jsx"
        )

        layout_file.write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

    # ==================================================================
    # HELPERS
    # ==================================================================

    @staticmethod
    def _to_css_name(
        value: str,
    ) -> str:
        """Convert a component/page/layout name into a CSS-friendly name."""

        value = re.sub(
            r"(?<!^)(?=[A-Z])",
            "-",
            value,
        )

        value = re.sub(
            r"[^a-zA-Z0-9_-]",
            "-",
            value,
        )

        return value.lower().strip("-")