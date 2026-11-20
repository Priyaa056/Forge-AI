"""UI Agent: designs pages, navigation, forms and API needs, then generates the React frontend.

Input: requirements (PM). Output: ``ui_spec.json`` (UIOutput) + ``frontend/`` source code.
"""

import re
from typing import Any, Dict, List, Optional

from backend.agents.base_agent import BaseAgent
from backend.artifacts.artifact_context import ArtifactContext
from backend.codegen.blueprint import build_blueprint
from backend.codegen.frontend_writer import build_ui_spec, write_frontend_files
from backend.exceptions import GenerationError
from backend.llm.client import LLMError, extract_json
from backend.schemas.pm_schema import PMOutput
from backend.schemas.ui_schema import UIOutput

AGENT = "ui"
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class UIAgent(BaseAgent[UIOutput]):
    stage_name = AGENT

    def __init__(
        self,
        pm_output_path: str = "outputs/pm_output.json",
        output_filepath: str = "outputs/ui_output.json",
        artifact_context: Optional[ArtifactContext] = None,
        project: Optional[Any] = None,
        log_fn=None,
        backend_output_path: Optional[str] = None,  # accepted for backwards compatibility (unused)
        reuse_styling: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(output_schema_cls=UIOutput, output_filepath=output_filepath,
                         artifact_context=artifact_context, project=project, log_fn=log_fn)
        self.pm_output_path = pm_output_path
        self.pm_data: Optional[PMOutput] = None
        self.ui_spec: Optional[Dict[str, Any]] = None
        # refinements keep the previous version's visual identity (colours the user asks for still win)
        self.reuse_styling = reuse_styling

    def load_inputs(self) -> None:
        self.pm_data = self.load_upstream("pm", PMOutput, self.pm_output_path)
        if not self.pm_data.project_name:
            raise GenerationError("PM output has no project_name")

    def _llm_styling(self, client, bp) -> Dict[str, Any]:
        prompt = (
            "You are the UI/UX agent of FORGE AI. For the application below choose a visual identity. Return ONLY JSON: "
            '{"primary_color": "#RRGGBB (accessible on white)", "tagline": "one sentence shown on the dashboard", '
            '"design_system_notes": "one sentence"}\n\n'
            f"Application: {bp.project_name}\nPurpose: {bp.purpose or bp.description[:300]}\n"
            f"Modules: {', '.join(m.label for m in bp.modules)}"
        )
        data = extract_json(client.generate_text(prompt, json_mode=True))
        styling: Dict[str, Any] = {}
        color = str(data.get("primary_color", "")).strip()
        if HEX_COLOR.match(color):
            styling["primary_color"] = color
        tagline = str(data.get("tagline", "")).strip()
        if 5 <= len(tagline) <= 200:
            styling["tagline"] = tagline
        notes = str(data.get("design_system_notes", "")).strip()
        if notes:
            styling["design_system_notes"] = notes[:300]
        if not styling:
            raise LLMError("LLM styling response contained no usable values")
        return styling

    def generate(self) -> Dict[str, Any]:
        bp = build_blueprint(self.pm_data)
        styling: Dict[str, Any] = {}
        client = self.get_llm()
        if self.reuse_styling is not None:
            styling = {k: v for k, v in self.reuse_styling.items()
                       if k in ("primary_color", "tagline", "design_system_notes") and v}
            client = None
            self.log("Keeping the visual identity of the previous version")
        if client is not None:
            try:
                styling = self._llm_styling(client, bp)
                self.generation_mode = "llm"
                self.log(f"LLM design decisions: {styling}")
            except (LLMError, ValueError) as exc:
                self.generation_mode = "deterministic_fallback"
                self.log(f"LLM styling failed ({str(exc)[:150]}); using the default theme", "warning")
        spec = build_ui_spec(bp, styling)
        if styling.get("tagline"):
            spec["styling_requirements"]["tagline"] = styling["tagline"]
        self.ui_spec = spec
        self.log(f"Designed {len(spec['pages'])} pages, {len(spec['forms'])} forms, "
                 f"{len(spec['api_requirements'])} API calls; theme {spec['styling_requirements']['primary_color']}")
        return spec

    def emit_code(self, output: UIOutput) -> List[str]:
        bp = build_blueprint(self.pm_data)
        spec = output.model_dump()
        if self.ui_spec and self.ui_spec.get("styling_requirements", {}).get("tagline"):
            spec["styling_requirements"]["tagline"] = self.ui_spec["styling_requirements"]["tagline"]
        return write_frontend_files(bp, self.project, spec)
