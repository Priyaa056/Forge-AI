"""Pipeline Orchestration Engine for FORGE AI Multi-Agent System."""

import os
import json
import uuid
import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from pydantic import BaseModel, Field

from backend.schemas.pm_schema import PMOutput
from backend.schemas.ui_schema import UIOutput, PageComponentSpec, UIComponentSpec
from backend.schemas.backend_schema import BackendOutput, EndpointSpec, ResponseSchemaSpec, ServiceLayerSpec
from backend.schemas.db_schema import DBOutput, AlembicMetadata
from backend.schemas.auth_schema import AuthOutput, PasswordSecuritySpec, JWTStrategySpec
from backend.schemas.qa_schema import QAOutput
from backend.schemas.deploy_schema import DeployOutput

logger = logging.getLogger("forge_pipeline")


class AgentStatus(str, Enum):
    """Execution status for individual agents and overall pipeline."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class PipelineStage(str, Enum):
    """Pipeline agent stages in execution order."""
    PM = "pm"
    UI = "ui"
    BACKEND = "backend"
    DB = "db"
    AUTH = "auth"
    QA = "qa"
    DEPLOY = "deploy"


STAGE_ORDER = [
    PipelineStage.PM,
    PipelineStage.UI,
    PipelineStage.BACKEND,
    PipelineStage.DB,
    PipelineStage.AUTH,
    PipelineStage.QA,
    PipelineStage.DEPLOY,
]

STAGE_SCHEMA_MAP = {
    PipelineStage.PM: PMOutput,
    PipelineStage.UI: UIOutput,
    PipelineStage.BACKEND: BackendOutput,
    PipelineStage.DB: DBOutput,
    PipelineStage.AUTH: AuthOutput,
    PipelineStage.QA: QAOutput,
    PipelineStage.DEPLOY: DeployOutput,
}


class PipelineExecutionState(BaseModel):
    """Data model representing current state of pipeline execution."""
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_prompt: str = Field(default="", description="User application idea prompt")
    execution_status: AgentStatus = Field(default=AgentStatus.PENDING)
    current_agent: Optional[PipelineStage] = Field(default=None)
    agent_statuses: Dict[PipelineStage, AgentStatus] = Field(
        default_factory=lambda: {stage: AgentStatus.PENDING for stage in STAGE_ORDER}
    )
    agent_outputs: Dict[str, Any] = Field(default_factory=dict)
    error_reports: Dict[str, str] = Field(default_factory=dict)
    output_dir: str = Field(default="outputs")


class ForgePipeline:
    """Orchestrates 7-stage execution: PM -> UI -> Backend -> DB -> Auth -> QA -> Deploy."""

    def __init__(
        self,
        user_prompt: str = "",
        project_id: Optional[str] = None,
        output_dir: str = "outputs",
        agent_handlers: Optional[Dict[PipelineStage, Callable[[Dict[str, Any]], Dict[str, Any]]]] = None,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.state = PipelineExecutionState(
            project_id=project_id or f"proj_{uuid.uuid4().hex[:8]}",
            user_prompt=user_prompt,
            output_dir=str(self.output_dir),
        )

        # Optional custom handler hooks (e.g. for plugging in actual agent implementations or mocks)
        self.agent_handlers: Dict[PipelineStage, Callable[[Dict[str, Any]], Dict[str, Any]]] = (
            agent_handlers or {}
        )

    def register_agent_handler(
        self,
        stage: PipelineStage,
        handler: Callable[[Dict[str, Any]], Dict[str, Any]]
    ):
        """Register a custom handler or agent runner for a specific stage."""
        self.agent_handlers[stage] = handler

    def execute_pm_stage(self) -> PMOutput:
        """Default PM stage implementation using existing pm_output.json or mock fallback."""
        pm_output_file = self.output_dir / "pm_output.json"

        if PipelineStage.PM in self.agent_handlers:
            raw_output = self.agent_handlers[PipelineStage.PM]({"user_prompt": self.state.user_prompt})
            pm_out = PMOutput.model_validate(raw_output)
        elif pm_output_file.exists():
            with open(pm_output_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            pm_out = PMOutput.model_validate(data)
        else:
            pm_out = PMOutput(
                project_name="TaskFlow",
                description=self.state.user_prompt or "Task management application",
                features=["User authentication", "Task CRUD operations"],
                tech_stack={"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
                database_entities=[]
            )

        with open(pm_output_file, "w", encoding="utf-8") as f:
            f.write(pm_out.model_dump_json(indent=2))

        return pm_out

    def execute_placeholder_stage(self, stage: PipelineStage) -> BaseModel:
        """Executes a placeholder/fallback runner for unbuilt agent stages."""
        pm_output = self.state.agent_outputs.get(PipelineStage.PM.value, {})
        project_name = pm_output.get("project_name", "GeneratedApp")

        if stage == PipelineStage.UI:
            data = UIOutput(
                project_name=project_name,
                framework="React",
                styling="Tailwind CSS",
                pages=[
                    PageComponentSpec(
                        name="Dashboard",
                        path="/",
                        components=["Navbar", "TaskCard"],
                        description="Main app dashboard"
                    )
                ],
                components=[
                    UIComponentSpec(
                        name="Navbar",
                        description="Navigation header",
                        props=[{"name": "title", "type": "string"}]
                    )
                ],
                design_system={"theme": "dark", "primaryColor": "#3b82f6"},
                routes=[{"path": "/", "component": "Dashboard"}]
            )
        elif stage == PipelineStage.BACKEND:
            data = BackendOutput(
                project_name=project_name,
                architecture="Clean Architecture (Controller-Service-Repository)",
                endpoints=[
                    EndpointSpec(
                        path="/api/health",
                        method="GET",
                        summary="Health check",
                        description="Check API status and connectivity",
                        operation_id="get_health",
                        tags=["Health"],
                        requires_auth=False,
                        required_roles=[],
                        request_schema=None,
                        response_schema=ResponseSchemaSpec(
                            name="HealthResponse",
                            status_code=200,
                            fields=[]
                        ),
                        parameters=[],
                        business_logic_summary="Returns server health status"
                    )
                ],
                service_layer=[
                    ServiceLayerSpec(
                        name="HealthService",
                        entity="System",
                        methods=[]
                    )
                ],
                repository_layer=[],
                global_dependencies=["get_db"],
                error_handlers=[]
            )
        elif stage == PipelineStage.DB:
            data = DBOutput(
                project_name=project_name,
                database_system="PostgreSQL",
                tables=[],
                sqlalchemy_models_code="# SQLAlchemy Models Placeholder",
                alembic_metadata=AlembicMetadata(
                    revision_id="init_001",
                    description="Initial migration schema",
                    upgrade_instructions=["op.create_table(...)"],
                    downgrade_instructions=["op.drop_table(...)"]
                )
            )
        elif stage == PipelineStage.AUTH:
            data = AuthOutput(
                project_name=project_name,
                password_security=PasswordSecuritySpec(),
                jwt_strategy=JWTStrategySpec(),
                auth_endpoints=[],
                rbac_roles=[]
            )
        elif stage == PipelineStage.QA:
            data = QAOutput(
                project_name=project_name,
                total_tests=5,
                passed_tests=5,
                failed_tests=0,
                coverage_percentage=100.0,
                lint_status="PASSED",
                security_scan_status="PASSED"
            )
        elif stage == PipelineStage.DEPLOY:
            data = DeployOutput(
                project_name=project_name,
                deployment_target="Docker",
                container_status="SUCCESS",
                health_check_status="HEALTHY"
            )
        else:
            raise ValueError(f"Unknown pipeline stage: {stage}")

        output_file = self.output_dir / f"{stage.value}_output.json"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=2))

        return data

    def run_stage(self, stage: PipelineStage) -> BaseModel:
        """Run single stage with status updates and error handling."""
        self.state.current_agent = stage
        self.state.agent_statuses[stage] = AgentStatus.RUNNING
        logger.info(f"Running pipeline stage: {stage.value}")

        try:
            if stage in self.agent_handlers:
                context = {
                    "user_prompt": self.state.user_prompt,
                    "previous_outputs": self.state.agent_outputs,
                    "output_dir": str(self.output_dir)
                }
                raw_out = self.agent_handlers[stage](context)
                schema_cls = STAGE_SCHEMA_MAP[stage]
                validated_out = schema_cls.model_validate(raw_out)
            elif stage == PipelineStage.PM:
                validated_out = self.execute_pm_stage()
            else:
                validated_out = self.execute_placeholder_stage(stage)

            self.state.agent_outputs[stage.value] = validated_out.model_dump()
            self.state.agent_statuses[stage] = AgentStatus.COMPLETED

            stage_path = self.output_dir / f"{stage.value}_output.json"
            with open(stage_path, "w", encoding="utf-8") as f:
                f.write(validated_out.model_dump_json(indent=2))

            return validated_out

        except Exception as e:
            self.state.agent_statuses[stage] = AgentStatus.FAILED
            self.state.error_reports[stage.value] = str(e)
            self.state.execution_status = AgentStatus.FAILED
            logger.error(f"Error in pipeline stage {stage.value}: {e}")
            raise e

    def retry_stage(self, stage: PipelineStage) -> BaseModel:
        """Retry a failed stage."""
        logger.info(f"Retrying pipeline stage: {stage.value}")
        self.state.agent_statuses[stage] = AgentStatus.RETRYING
        if stage.value in self.state.error_reports:
            del self.state.error_reports[stage.value]
        return self.run_stage(stage)

    def run_pipeline(self) -> PipelineExecutionState:
        """Execute full PM -> UI -> Backend -> DB -> Auth -> QA -> Deploy pipeline."""
        self.state.execution_status = AgentStatus.RUNNING

        for stage in STAGE_ORDER:
            try:
                self.run_stage(stage)
            except Exception:
                self.state.execution_status = AgentStatus.FAILED
                self.state.current_agent = stage
                return self.state

        self.state.execution_status = AgentStatus.COMPLETED
        self.state.current_agent = None
        return self.state

    def get_status_summary(self) -> Dict[str, Any]:
        """Returns JSON dashboard summary of current pipeline execution state."""
        return {
            "project_id": self.state.project_id,
            "user_prompt": self.state.user_prompt,
            "execution_status": self.state.execution_status.value,
            "current_agent": self.state.current_agent.value if self.state.current_agent else None,
            "agent_statuses": {
                stage.value: status.value for stage, status in self.state.agent_statuses.items()
            },
            "error_reports": self.state.error_reports,
            "completed_stages": [
                stage.value for stage, status in self.state.agent_statuses.items()
                if status == AgentStatus.COMPLETED
            ],
            "output_directory": str(self.output_dir),
        }
