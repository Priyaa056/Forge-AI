"""Artifact Context Layer for FORGE AI Multi-Agent System."""

from typing import Dict, Any, List, Optional, Type, TypeVar, Union
from pydantic import BaseModel, ValidationError

from backend.artifacts.artifact_schema import Artifact, ArtifactStatus
from backend.artifacts.artifact_manager import ArtifactManager, ArtifactValidationError


class ArtifactNotFoundError(Exception):
    """Raised when a requested artifact cannot be found in the store or context."""
    pass


T = TypeVar("T", bound=BaseModel)


class ArtifactContext:
    """Canonical context layer wrapping ArtifactManager to provide agent input retrieval,

    schema validation, and lineage tracking.
    """

    def __init__(
        self,
        artifact_manager: ArtifactManager,
        project_id: str,
        run_id: str,
        current_agent: Optional[str] = None,
        user_prompt: str = "",
        input_artifact_ids: Optional[List[str]] = None,
    ):
        self.artifact_manager = artifact_manager
        self.project_id = project_id
        self.run_id = run_id
        self.current_agent = current_agent
        self.user_prompt = user_prompt
        self.input_artifact_ids = input_artifact_ids or []

    def get_latest_artifact(self, agent_name: str) -> Optional[Artifact]:
        """Retrieve latest artifact for a specific agent in the project."""
        return self.artifact_manager.get_latest_artifact(self.project_id, agent_name)

    def get_artifact_by_id(self, artifact_id: str) -> Optional[Artifact]:
        """Retrieve a specific artifact by its unique artifact_id."""
        return self.artifact_manager.get_artifact(artifact_id)

    def get_input_artifacts(self) -> List[Artifact]:
        """Retrieve all input artifacts matching input_artifact_ids."""
        artifacts = []
        for art_id in self.input_artifact_ids:
            art = self.get_artifact_by_id(art_id)
            if art:
                artifacts.append(art)
            else:
                raise ArtifactNotFoundError(f"Input artifact '{art_id}' not found.")
        return artifacts

    def get_validated_content(
        self,
        agent_name_or_id: str,
        schema_cls: Type[T],
        optional: bool = False
    ) -> Optional[T]:
        """Retrieve and schema-validate artifact content for an agent or by artifact ID.

        If optional is True and artifact is missing, returns None.
        If artifact status is FAILED or content fails validation, raises ArtifactValidationError.
        """
        artifact = self.get_artifact_by_id(agent_name_or_id)
        if not artifact:
            artifact = self.get_latest_artifact(agent_name_or_id)

        if not artifact:
            if optional:
                return None
            raise ArtifactNotFoundError(
                f"Required artifact for '{agent_name_or_id}' not found in project '{self.project_id}'."
            )

        if artifact.status == ArtifactStatus.FAILED:
            raise ArtifactValidationError(
                f"Cannot consume failed artifact '{artifact.artifact_id}' from agent '{artifact.agent_name}'."
            )

        try:
            return schema_cls.model_validate(artifact.content)
        except ValidationError as e:
            raise ArtifactValidationError(
                f"Artifact content for '{artifact.agent_name}' failed validation against {schema_cls.__name__}: {e}"
            )
