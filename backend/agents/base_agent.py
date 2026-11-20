"""Abstract Base Agent defining the lifecycle contract shared by all seven FORGE AI agents.

Lifecycle: load_inputs -> generate (spec) -> validate (Pydantic contract) -> save_output (JSON spec)
-> emit_code (write project files owned by this agent).

Agents consume upstream outputs through :class:`ArtifactContext` (artifacts of the *current run*),
falling back to explicit JSON file paths for standalone use and backwards compatibility.
"""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError as PydanticValidationError

from backend.artifacts.artifact_context import ArtifactContext
from backend.exceptions import GenerationError, MissingInputError, ValidationError
from backend.llm.client import get_llm_client

T = TypeVar("T", bound=BaseModel)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class _LegacyResponse:
    def __init__(self, text: str):
        self.text = text


class _LLMModelAdapter:
    """Adapts the LLM client to the ``generate_content(prompt).text`` interface used by older agent code."""

    def __init__(self, client):
        self._client = client

    def generate_content(self, prompt: str):
        return _LegacyResponse(self._client.generate_text(prompt, json_mode=True))


class BaseAgent(ABC, Generic[T]):
    """Abstract Base Agent class enforcing a standard lifecycle and validation contract."""

    stage_name: str = "agent"

    def __init__(
        self,
        output_schema_cls: Type[T],
        output_filepath: str,
        artifact_context: Optional[ArtifactContext] = None,
        pipeline_logger: Optional[Any] = None,
        project: Optional[Any] = None,
        log_fn: Optional[Callable[[str, str], None]] = None,
    ):
        self.output_schema_cls = output_schema_cls
        self.output_filepath = Path(output_filepath)
        self.artifact_context = artifact_context
        self.pipeline_logger = pipeline_logger
        self.project = project  # GeneratedProject or None (spec-only mode)
        self.log_fn = log_fn
        self.logger = logging.getLogger(self.__class__.__name__)
        self.inputs: Dict[str, Any] = {}
        self.generated_data: Optional[Dict[str, Any]] = None
        self.validated_output: Optional[T] = None
        self.generated_files: List[str] = []
        self.generation_mode: str = "deterministic"
        self.notes: List[str] = []

    # ------------------------------------------------------------------ logging
    def log(self, message: str, level: str = "info") -> None:
        getattr(self.logger, level if level in ("info", "warning", "error") else "info")(message)
        if level == "warning":
            self.notes.append(message)
        if self.log_fn:
            try:
                self.log_fn(message, level)
            except Exception:  # monitoring must never break an agent
                pass

    # ------------------------------------------------------------------ LLM
    def get_llm(self):
        return get_llm_client()

    def get_gemini_model(self) -> Optional[Any]:
        """Backwards-compatible accessor returning an object with ``generate_content`` or None."""
        client = get_llm_client()
        return _LLMModelAdapter(client) if client is not None else None

    def parse_and_validate_llm_output(self, llm_text: str) -> Dict[str, Any]:
        """Parse raw LLM output text and validate against self.output_schema_cls.

        Raises ValidationError if output is malformed JSON or fails Pydantic schema validation.
        """
        agent_name = self.__class__.__name__
        cleaned_text = llm_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()

        try:
            parsed = json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            self.logger.error(f"[{agent_name}] LLM returned malformed JSON: {e}")
            raise ValidationError(f"[{agent_name}] LLM schema validation failed: malformed JSON ({str(e)})") from e

        try:
            self.output_schema_cls.model_validate(parsed)
            return parsed
        except PydanticValidationError as e:
            self.logger.error(f"[{agent_name}] LLM output schema validation failed: {e}")
            raise ValidationError(f"[{agent_name}] LLM schema validation failed: {str(e)}") from e

    # ------------------------------------------------------------------ inputs
    def read_json_file(self, filepath: str) -> Dict[str, Any]:
        """Read and parse a JSON input file."""
        path = Path(filepath)
        if not path.is_file():
            raise MissingInputError(f"Required input file not found: '{filepath}'")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON format in file '{filepath}': {str(e)}")

    def load_upstream(self, stage: str, schema_cls: Type[BaseModel], fallback_path: Optional[str],
                      optional: bool = False) -> Optional[BaseModel]:
        """Load an upstream agent output from the current run's artifacts, or from a JSON file."""
        if self.artifact_context is not None:
            return self.artifact_context.get_validated_content(stage, schema_cls, optional=optional)
        if fallback_path and Path(fallback_path).is_file():
            raw = self.read_json_file(fallback_path)
            try:
                return schema_cls.model_validate(raw)
            except PydanticValidationError as e:
                raise ValidationError(f"Invalid {Path(fallback_path).name} format: {e}")
        if optional:
            return None
        raise MissingInputError(f"Required input from '{stage}' not found (path: {fallback_path})")

    # ------------------------------------------------------------------ lifecycle
    @abstractmethod
    def load_inputs(self) -> None:
        """Load and parse all inputs required for this agent."""

    @abstractmethod
    def generate(self) -> Dict[str, Any]:
        """Generate the specification data dictionary using LLM or rule-based logic."""

    def emit_code(self, output: T) -> List[str]:
        """Write the project files this agent owns. Default: no files."""
        return []

    def validate(self) -> T:
        """Validate generated raw data against the agent's Pydantic schema."""
        if self.generated_data is None:
            raise GenerationError(f"{self.__class__.__name__}: Cannot validate before generation.")
        try:
            self.validated_output = self.output_schema_cls.model_validate(self.generated_data)
            self.logger.info(f"{self.__class__.__name__} successfully validated generated specification.")
            return self.validated_output
        except PydanticValidationError as e:
            self.logger.error(f"{self.__class__.__name__} schema validation failed: {e}")
            raise ValidationError(f"Output validation failed for {self.__class__.__name__}: {str(e)}")

    def save_output(self) -> Path:
        """Save validated output specification to destination file."""
        if self.validated_output is None:
            raise GenerationError(f"{self.__class__.__name__}: Cannot save output before validation.")
        try:
            self.output_filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self.output_filepath, "w", encoding="utf-8") as f:
                json.dump(self.validated_output.model_dump(), f, indent=2)
            self.logger.info(f"Saved generated output to '{self.output_filepath}'")
            return self.output_filepath
        except Exception as e:
            raise GenerationError(f"Failed to save output to '{self.output_filepath}': {str(e)}")

    def run(self) -> T:
        """Execute complete agent lifecycle: load -> generate -> validate -> save -> emit code."""
        self.logger.info(f"Starting {self.__class__.__name__} execution...")
        self.load_inputs()
        self.generated_data = self.generate()
        validated = self.validate()
        self.save_output()
        if self.project is not None:
            self.generated_files = self.emit_code(validated) or []
            if self.generated_files:
                self.log(f"Wrote {len(self.generated_files)} file(s) to the generated project")
        self.logger.info(f"{self.__class__.__name__} execution completed successfully.")
        return validated

    def result_metadata(self) -> Dict[str, Any]:
        return {
            "generation_mode": self.generation_mode,
            "generated_files": self.generated_files,
            "notes": self.notes,
        }
