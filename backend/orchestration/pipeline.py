"""Pipeline Orchestration Engine for FORGE AI Multi-Agent System."""

import json
import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, Callable, Union
from pydantic import BaseModel, Field

from backend.schemas.pm_schema import PMOutput
from backend.agents.backend_agent import BackendAgent
from backend.agents.db_agent import DBAgent
from backend.agents.auth_agent import AuthAgent
from backend.agents.ui_agent import UIAgent
from backend.agents.react_generator import ReactGenerator

logger = logging.getLogger(__name__)


class PipelineStage(str, Enum):
    IDLE = "IDLE"
    PM_SPEC_LOADED = "PM_SPEC_LOADED"
    BACKEND_GENERATED = "BACKEND_GENERATED"
    DB_GENERATED = "DB_GENERATED"
    AUTH_GENERATED = "AUTH_GENERATED"
    UI_GENERATED = "UI_GENERATED"
    REACT_CODE_GENERATED = "REACT_CODE_GENERATED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PipelineResult(BaseModel):
    success: bool
    final_stage: PipelineStage
    artifacts: Dict[str, str] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class PipelineOrchestrationEngine:
    """Engine that orchestrates multi-agent code generation across system pipeline stages."""

    def __init__(
        self,
        output_dir: Union[str, Path] = "outputs",
        progress_callback: Optional[Callable[[PipelineStage, str], None]] = None,
    ):
        self.output_dir = Path(output_dir).resolve()
        self.progress_callback = progress_callback
        self._current_stage: PipelineStage = PipelineStage.IDLE
        self._artifacts: Dict[str, str] = {}
        self._outputs: Dict[str, Any] = {}
        self._error: Optional[str] = None

    @property
    def current_stage(self) -> PipelineStage:
        return self._current_stage

    @property
    def artifacts(self) -> Dict[str, str]:
        return self._artifacts

    @property
    def error(self) -> Optional[str]:
        return self._error

    def _notify(self, stage: PipelineStage, message: str) -> None:
        self._current_stage = stage
        logger.info(f"[{stage.value}] {message}")
        if self.progress_callback:
            try:
                self.progress_callback(stage, message)
            except Exception as e:
                logger.warning(f"Progress callback failed for stage {stage.value}: {e}")

    def run(self, pm_spec: Union[PMOutput, Dict[str, Any]]) -> PipelineResult:
        """Executes full multi-agent pipeline given a PM spec specification."""
        self._artifacts.clear()
        self._outputs.clear()
        self._error = None
        self._current_stage = PipelineStage.IDLE

        try:
            # Step 0: Ensure target directory structure exists
            self.output_dir.mkdir(parents=True, exist_ok=True)
            pm_path = self.output_dir / "pm_output.json"
            backend_path = self.output_dir / "backend_output.json"
            db_path = self.output_dir / "db_output.json"
            auth_path = self.output_dir / "auth_output.json"
            ui_path = self.output_dir / "ui_output.json"
            frontend_dir = self.output_dir / "frontend"

            # Step 1: PM Specification Validation & File Persistence
            self._notify(PipelineStage.IDLE, "Validating PM specification...")
            if isinstance(pm_spec, PMOutput):
                validated_pm = pm_spec
            elif isinstance(pm_spec, dict):
                validated_pm = PMOutput(**pm_spec)
            else:
                raise ValueError(f"Invalid PM specification type: {type(pm_spec)}")

            pm_path.write_text(validated_pm.model_dump_json(indent=2), encoding="utf-8")
            self._artifacts["pm_spec"] = str(pm_path)
            self._outputs["pm_spec"] = validated_pm.model_dump()
            self._notify(PipelineStage.PM_SPEC_LOADED, "PM specification validated and saved.")

            # Step 2: Backend Generation Stage
            self._notify(PipelineStage.PM_SPEC_LOADED, "Running BackendAgent...")
            backend_agent = BackendAgent(
                pm_output_path=str(pm_path),
                output_filepath=str(backend_path),
            )
            backend_out = backend_agent.run()
            self._artifacts["backend_spec"] = str(backend_path)
            self._outputs["backend_spec"] = backend_out.model_dump()
            self._notify(PipelineStage.BACKEND_GENERATED, "Backend specifications generated.")

            # Step 3: Database Generation Stage
            self._notify(PipelineStage.BACKEND_GENERATED, "Running DBAgent...")
            db_agent = DBAgent(
                pm_output_path=str(pm_path),
                backend_output_path=str(backend_path),
                output_filepath=str(db_path),
            )
            db_out = db_agent.run()
            self._artifacts["db_spec"] = str(db_path)
            self._outputs["db_spec"] = db_out.model_dump()
            self._notify(PipelineStage.DB_GENERATED, "Database specifications generated.")

            # Step 4: Authentication Generation Stage
            self._notify(PipelineStage.DB_GENERATED, "Running AuthAgent...")
            auth_agent = AuthAgent(
                pm_output_path=str(pm_path),
                backend_output_path=str(backend_path),
                db_output_path=str(db_path),
                output_filepath=str(auth_path),
            )
            auth_out = auth_agent.run()
            self._artifacts["auth_spec"] = str(auth_path)
            self._outputs["auth_spec"] = auth_out.model_dump()
            self._notify(PipelineStage.AUTH_GENERATED, "Authentication specifications generated.")

            # Step 5: UI Specification Generation Stage
            self._notify(PipelineStage.AUTH_GENERATED, "Running UIAgent...")
            ui_agent = UIAgent(
                pm_output_path=str(pm_path),
                output_filepath=str(ui_path),
            )
            ui_out = ui_agent.run()
            self._artifacts["ui_spec"] = str(ui_path)
            self._outputs["ui_spec"] = ui_out.model_dump()
            self._notify(PipelineStage.UI_GENERATED, "UI specifications generated.")

            # Step 6: React Frontend Code Generation Stage
            self._notify(PipelineStage.UI_GENERATED, "Running ReactGenerator...")
            react_generator = ReactGenerator(
                ui_output_path=str(ui_path),
                output_dir=str(frontend_dir),
            )
            generated_frontend_path = react_generator.run()
            self._artifacts["frontend_dir"] = str(generated_frontend_path)
            self._notify(PipelineStage.REACT_CODE_GENERATED, "React frontend application generated.")

            # Step 7: Completion
            self._notify(PipelineStage.COMPLETED, "Pipeline execution completed successfully.")
            return PipelineResult(
                success=True,
                final_stage=PipelineStage.COMPLETED,
                artifacts=dict(self._artifacts),
                outputs=dict(self._outputs),
                error=None,
            )

        except Exception as exc:
            self._error = str(exc)
            logger.error(f"Pipeline execution failed at stage {self._current_stage.value}: {exc}", exc_info=True)
            self._notify(PipelineStage.FAILED, f"Pipeline failed: {exc}")
            return PipelineResult(
                success=False,
                final_stage=PipelineStage.FAILED,
                artifacts=dict(self._artifacts),
                outputs=dict(self._outputs),
                error=self._error,
            )
