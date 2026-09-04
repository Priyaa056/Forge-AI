"""Artifact Store abstraction and local filesystem JSON implementation."""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional
from backend.artifacts.artifact_schema import Artifact


class BaseArtifactStore(ABC):
    """Abstract interface for storing and retrieving FORGE AI artifacts."""

    @abstractmethod
    def save(self, artifact: Artifact) -> None:
        """Persist an artifact to storage."""
        pass

    @abstractmethod
    def get(self, artifact_id: str) -> Optional[Artifact]:
        """Retrieve an artifact by its unique artifact_id."""
        pass

    @abstractmethod
    def get_by_version(self, project_id: str, agent_name: str, version: int) -> Optional[Artifact]:
        """Retrieve a specific version of an agent's artifact for a given project."""
        pass

    @abstractmethod
    def get_latest(self, project_id: str, agent_name: str) -> Optional[Artifact]:
        """Retrieve the highest version of an agent's artifact for a given project."""
        pass

    @abstractmethod
    def list(
        self,
        project_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> List[Artifact]:
        """List artifacts filtered by optional parameters."""
        pass


class LocalJsonArtifactStore(BaseArtifactStore):
    """Local filesystem JSON persistent storage implementation for artifacts."""

    def __init__(self, storage_dir: str = "data/artifacts"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_artifact_path(self, artifact: Artifact) -> Path:
        proj_dir = self.storage_dir / artifact.project_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{artifact.agent_name}_v{artifact.version}_{artifact.artifact_id}.json"
        return proj_dir / filename

    def save(self, artifact: Artifact) -> None:
        file_path = self._get_artifact_path(artifact)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(artifact.model_dump_json(indent=2))

    def _load_all_artifacts(self) -> List[Artifact]:
        artifacts: List[Artifact] = []
        if not self.storage_dir.exists():
            return artifacts

        for json_file in self.storage_dir.glob("**/*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                artifacts.append(Artifact.model_validate(data))
            except Exception:
                # Ignore corrupt/non-artifact files
                continue
        return artifacts

    def get(self, artifact_id: str) -> Optional[Artifact]:
        for artifact in self._load_all_artifacts():
            if artifact.artifact_id == artifact_id:
                return artifact
        return None

    def get_by_version(self, project_id: str, agent_name: str, version: int) -> Optional[Artifact]:
        for artifact in self._load_all_artifacts():
            if (
                artifact.project_id == project_id
                and artifact.agent_name == agent_name
                and artifact.version == version
            ):
                return artifact
        return None

    def get_latest(self, project_id: str, agent_name: str) -> Optional[Artifact]:
        matching = [
            art for art in self._load_all_artifacts()
            if art.project_id == project_id and art.agent_name == agent_name
        ]
        if not matching:
            return None
        # Sort by version descending (or created_at if tied)
        matching.sort(key=lambda x: (x.version, x.created_at), reverse=True)
        return matching[0]

    def list(
        self,
        project_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> List[Artifact]:
        artifacts = self._load_all_artifacts()
        filtered = []
        for art in artifacts:
            if project_id and art.project_id != project_id:
                continue
            if agent_name and art.agent_name != agent_name:
                continue
            if run_id and art.run_id != run_id:
                continue
            filtered.append(art)

        # Sort by created_at ascending
        filtered.sort(key=lambda x: x.created_at)
        return filtered
