"""Artifact Manager providing high-level operations, auto-versioning, lineage tracking, schema validation, and secret scanning."""

import re
from typing import Dict, Any, List, Optional, Type, Union
from pydantic import BaseModel, ValidationError

from backend.artifacts.artifact_schema import Artifact, ArtifactStatus
from backend.artifacts.artifact_store import BaseArtifactStore, LocalJsonArtifactStore


class ArtifactSecurityError(Exception):
    """Raised when an artifact contains sensitive information such as secrets or credentials."""
    pass


class ArtifactValidationError(Exception):
    """Raised when artifact contents fail schema validation or structural integrity checks."""
    pass


# Forbidden key patterns (case-insensitive)
SENSITIVE_KEY_PATTERNS = [
    r"api_?key",
    r"passw(?:or)?d",
    r"jwt_?secret",
    r"access_?token",
    r"auth_?token",
    r"private_?key",
    r"secret_?key",
    r"\.env",
]

# Sensitive value regex patterns
SENSITIVE_VALUE_REGEXES = [
    re.compile(r"sk-[a-zA-Z0-9_-]{16,}"),
    re.compile(r"AIza[0-9A-Za-z-_]{35}"),
    re.compile(r"Bearer\s+eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+"),
    re.compile(r"eyJ[A-Za-z0-9-_=]{10,}\.[A-Za-z0-9-_=]{10,}"),
]


EXEMPT_SENSITIVE_KEYS = {
    "password_security",
    "password_policy",
    "password_hash_algorithm",
    "password_reset_workflow",
    "access_token_expire_minutes",
    "refresh_token_expire_days",
    "secret_key_env_var",
    "hashed_password",
}


def _scan_for_secrets(data: Any, path: str = "") -> None:
    """Recursively scan data structures for sensitive keys or value patterns."""
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else str(key)
            key_lower = str(key).lower()
            if key_lower in EXEMPT_SENSITIVE_KEYS:
                _scan_for_secrets(value, current_path)
                continue
            for pattern in SENSITIVE_KEY_PATTERNS:
                if re.search(pattern, key_lower):
                    # Check if value is not empty/null
                    if value is not None and value != "":
                        raise ArtifactSecurityError(
                            f"Security Violation: Sensitive key '{key}' detected at path '{current_path}'."
                        )
            _scan_for_secrets(value, current_path)
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            _scan_for_secrets(item, f"{path}[{idx}]")
    elif isinstance(data, str):
        for regex in SENSITIVE_VALUE_REGEXES:
            if regex.search(data):
                raise ArtifactSecurityError(
                    f"Security Violation: Sensitive token pattern detected at path '{path}'."
                )


class ArtifactManager:
    """Manager class for managing agent artifact lifecycle, versioning, lineage, and validation."""

    def __init__(self, store: Optional[BaseArtifactStore] = None):
        self.store = store or LocalJsonArtifactStore()

    def create_artifact(
        self,
        project_id: str,
        run_id: str,
        agent_name: str,
        artifact_type: str,
        content: Union[Dict[str, Any], BaseModel],
        input_artifacts: Optional[List[str]] = None,
        status: ArtifactStatus = ArtifactStatus.COMPLETED,
        metadata: Optional[Dict[str, Any]] = None,
        schema_cls: Optional[Type[BaseModel]] = None,
    ) -> Artifact:
        """Creates, validates, versions, and persists a new Artifact."""

        # Convert Pydantic content model if provided
        if isinstance(content, BaseModel):
            content_dict = content.model_dump()
        elif isinstance(content, dict):
            content_dict = content
        else:
            raise ArtifactValidationError(
                f"Artifact content must be a Pydantic model or Dict, got {type(content).__name__}"
            )

        metadata_dict = metadata or {}
        input_artifacts_list = input_artifacts or []

        # Validate schema if schema_cls provided
        if schema_cls:
            try:
                schema_cls.model_validate(content_dict)
            except ValidationError as e:
                raise ArtifactValidationError(f"Artifact content failed schema validation for {schema_cls.__name__}: {e}")

        # Security scan on content and metadata
        _scan_for_secrets(content_dict, path="content")
        _scan_for_secrets(metadata_dict, path="metadata")

        # Determine versioning (next version for project_id + agent_name)
        latest = self.store.get_latest(project_id, agent_name)
        next_version = (latest.version + 1) if latest else 1

        artifact = Artifact(
            project_id=project_id,
            run_id=run_id,
            agent_name=agent_name,
            artifact_type=artifact_type,
            version=next_version,
            input_artifacts=input_artifacts_list,
            status=status,
            content=content_dict,
            metadata=metadata_dict,
        )

        self.store.save(artifact)
        return artifact

    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        """Get artifact by artifact_id."""
        return self.store.get(artifact_id)

    def get_latest_artifact(self, project_id: str, agent_name: str) -> Optional[Artifact]:
        """Get latest artifact version for a project and agent."""
        return self.store.get_latest(project_id, agent_name)

    def get_artifact_version(self, project_id: str, agent_name: str, version: int) -> Optional[Artifact]:
        """Get specific artifact version for a project and agent."""
        return self.store.get_by_version(project_id, agent_name, version)

    def list_artifacts(
        self,
        project_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> List[Artifact]:
        """List artifacts with optional filtering."""
        return self.store.list(project_id=project_id, agent_name=agent_name, run_id=run_id)

    def get_all_versions(self, project_id: str, agent_name: str) -> List[Artifact]:
        """Get all versions of an artifact for a specific agent and project, sorted by version."""
        artifacts = self.store.list(project_id=project_id, agent_name=agent_name)
        artifacts.sort(key=lambda a: a.version)
        return artifacts

    def validate_artifact(
        self,
        artifact: Union[Artifact, Dict[str, Any]],
        schema_cls: Optional[Type[BaseModel]] = None
    ) -> bool:
        """Validates artifact structural integrity, security compliance, and optional schema conformity."""
        if isinstance(artifact, dict):
            try:
                artifact_obj = Artifact.model_validate(artifact)
            except ValidationError as e:
                raise ArtifactValidationError(f"Invalid artifact format: {e}")
        else:
            artifact_obj = artifact

        # Security check
        _scan_for_secrets(artifact_obj.content, path="content")
        _scan_for_secrets(artifact_obj.metadata, path="metadata")

        # Schema check if provided
        if schema_cls:
            try:
                schema_cls.model_validate(artifact_obj.content)
            except ValidationError as e:
                raise ArtifactValidationError(f"Artifact content does not conform to {schema_cls.__name__}: {e}")

        return True
