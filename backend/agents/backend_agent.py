"""Backend Agent: designs the REST API contract and generates the FastAPI application.

Inputs: requirements (PM) and the UI agent's API requirements.
Output: ``api_spec.json`` (BackendOutput) + ``backend/app`` routers, schemas and entry point.
The agent fails if the UI agent requires an endpoint that the API contract does not provide.
"""

from typing import Any, Dict, List, Optional

from backend.agents.base_agent import BaseAgent
from backend.artifacts.artifact_context import ArtifactContext
from backend.codegen.backend_writer import build_api_spec, check_ui_contract, write_backend_files
from backend.codegen.blueprint import build_blueprint
from backend.exceptions import GenerationError, ValidationError
from backend.schemas.backend_schema import BackendOutput
from backend.schemas.pm_schema import PMOutput
from backend.schemas.ui_schema import UIOutput

AGENT = "backend"


class BackendAgent(BaseAgent[BackendOutput]):
    stage_name = AGENT

    def __init__(
        self,
        pm_output_path: str = "outputs/pm_output.json",
        ui_output_path: Optional[str] = "outputs/ui_output.json",
        output_filepath: str = "outputs/backend_output.json",
        artifact_context: Optional[ArtifactContext] = None,
        project: Optional[Any] = None,
        log_fn=None,
    ):
        super().__init__(output_schema_cls=BackendOutput, output_filepath=output_filepath,
                         artifact_context=artifact_context, project=project, log_fn=log_fn)
        self.pm_output_path = pm_output_path
        self.ui_output_path = ui_output_path
        self.pm_data: Optional[PMOutput] = None
        self.ui_data: Optional[UIOutput] = None

    def load_inputs(self) -> None:
        self.pm_data = self.load_upstream("pm", PMOutput, self.pm_output_path)
        self.ui_data = self.load_upstream("ui", UIOutput, self.ui_output_path, optional=True)

    def generate(self) -> Dict[str, Any]:
        if not self.pm_data:
            raise GenerationError("Inputs not loaded. Call load_inputs() first.")
        bp = build_blueprint(self.pm_data)
        spec = build_api_spec(bp)
        if self.ui_data is not None:
            coverage = check_ui_contract(spec, [r.model_dump() for r in self.ui_data.api_requirements])
            spec["ui_contract_coverage"] = coverage
            if coverage["missing"]:
                raise ValidationError(
                    "API contract does not cover endpoints required by the UI agent: " + ", ".join(coverage["missing"])
                )
            self.log(f"UI contract check: {len(coverage['covered'])} endpoints covered, "
                     f"{len(coverage['delegated_to_auth'])} delegated to the Auth agent, 0 missing")
        else:
            self.log("No UI specification available; skipping UI contract check", "warning")
        methods = {}
        for ep in spec["endpoints"]:
            methods[ep["method"]] = methods.get(ep["method"], 0) + 1
        self.log(f"Designed {len(spec['endpoints'])} endpoints ({', '.join(f'{k} {v}' for k, v in sorted(methods.items()))}) "
                 f"for {len(bp.entities)} resources")
        return spec

    def emit_code(self, output: BackendOutput) -> List[str]:
        files = write_backend_files(build_blueprint(self.pm_data), self.project)
        return files
