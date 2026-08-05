"""Abstract Base Agent class defining contract for FORGE AI Agents."""

import os
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Type, TypeVar, Generic, Optional

from pydantic import BaseModel, ValidationError as PydanticValidationError
import google.generativeai as genai
from dotenv import load_dotenv

from backend.exceptions import MissingInputError, ValidationError, GenerationError

# Load environment variables
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

T = TypeVar("T", bound=BaseModel)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class BaseAgent(ABC, Generic[T]):
    """Abstract Base Agent class enforcing standard lifecycle and validation contract."""

    def __init__(self, output_schema_cls: Type[T], output_filepath: str):
        self.output_schema_cls = output_schema_cls
        self.output_filepath = Path(output_filepath)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.inputs: Dict[str, Any] = {}
        self.generated_data: Optional[Dict[str, Any]] = None
        self.validated_output: Optional[T] = None

    def get_gemini_model(self) -> Optional[Any]:
        """Configure and return Gemini GenerativeModel if API key and USE_LLM are enabled."""
        if os.getenv("USE_LLM", "false").lower() != "true":
            return None
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key or api_key == "your_gemini_api_key_here":
            self.logger.warning("GOOGLE_API_KEY not configured. Falling back to rule-based agent generator.")
            return None
        try:
            genai.configure(api_key=api_key)
            return genai.GenerativeModel("gemini-2.0-flash")
        except Exception as e:
            self.logger.warning(f"Failed to configure Gemini model: {e}. Using rule-based fallback.")
            return None

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

    @abstractmethod
    def load_inputs(self) -> None:
        """Load and parse all input files required for this agent."""
        pass

    @abstractmethod
    def generate(self) -> Dict[str, Any]:
        """Generate specification data dictionary using LLM or rule-based logic."""
        pass

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
        """Execute complete agent lifecycle: load -> generate -> validate -> save."""
        self.logger.info(f"Starting {self.__class__.__name__} execution...")
        self.load_inputs()
        self.generated_data = self.generate()
        validated = self.validate()
        self.save_output()
        self.logger.info(f"{self.__class__.__name__} execution completed successfully.")
        return validated
