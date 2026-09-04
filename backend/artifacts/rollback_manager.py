"""Rollback & Recovery System for FORGE AI Artifacts."""

import uuid
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Type, Union
from pydantic import BaseModel, Field

from backend.artifacts.artifact_schema import Artifact, ArtifactStatus
from backend.artifacts.artifact_manager import (
    ArtifactManager,
    ArtifactSecurityError,
    ArtifactValidationError,
)
from backend.monitoring.logger import PipelineLogger, sanitize_secret

logger = logging.getLogger("rollback_manager")


class RollbackError(Exception):
    """Base exception for all rollback and recovery operations."""
    pass


class RollbackValidationError(RollbackError):
    """Raised when a target artifact fails validation (non-existent, failed status, invalid schema, or secret violation)."""
    pass


class RollbackDependencyError(RollbackError):
    """Raised when rolling back an upstream artifact would cause downstream pipeline inconsistencies."""
    pass


class RollbackResult(BaseModel):
    """Auditable result model for a rollback operation."""
    rollback_id: str = Field(default_factory=lambda: f"rb_{uuid.uuid4().hex[:12]}")
    project_id: str
    run_id: str
    agent_name: str
    source_artifact_id: Optional[str] = None
    source_version: Optional[int] = None
    target_artifact_id: str
    target_version: int
    restored_artifact_id: Optional[str] = None
    restored_version: Optional[int] = None
    status: str = Field(default="COMPLETED")  # "COMPLETED" or "FAILED"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: Optional[str] = None
    error_message: Optional[str] = None


STAGE_DOWNSTREAM_MAP: Dict[str, List[str]] = {
    "pm": ["ui", "backend", "db", "auth", "qa", "deploy"],
    "ui": ["backend", "qa", "deploy"],
    "backend": ["db", "auth", "qa", "deploy"],
    "db": ["auth", "qa", "deploy"],
    "auth": ["qa", "deploy"],
    "qa": ["deploy"],
    "deploy": [],
}


class RollbackManager:
    """Manager providing additive artifact rollback, target validation, lineage tracking, and dependency checking."""

    def __init__(
        self,
        artifact_manager: ArtifactManager,
        pipeline_logger: Optional[PipelineLogger] = None,
    ):
        self.artifact_manager = artifact_manager
        self.pipeline_logger = pipeline_logger or PipelineLogger()
        self._history: List[RollbackResult] = []

    def get_available_versions(self, project_id: str, agent_name: str) -> List[Artifact]:
        """Retrieve all versions of an artifact for a specific agent and project, sorted by version ascending."""
        return self.artifact_manager.get_all_versions(project_id, agent_name)

    def get_latest_valid_version(self, project_id: str, agent_name: str) -> Optional[Artifact]:
        """Retrieve the highest version artifact for an agent whose status is COMPLETED."""
        versions = self.get_available_versions(project_id, agent_name)
        valid = [art for art in versions if art.status == ArtifactStatus.COMPLETED]
        return valid[-1] if valid else None

    def get_downstream_dependents(self, agent_name: str) -> List[str]:
        """Get downstream stage names that depend on the specified agent."""
        return STAGE_DOWNSTREAM_MAP.get(agent_name, [])

    def check_dependency_conflicts(self, project_id: str, agent_name: str) -> List[str]:
        """Identify active downstream artifacts in project_id that depend on agent_name."""
        dependents = self.get_downstream_dependents(agent_name)
        conflicts = []
        for dep in dependents:
            latest = self.artifact_manager.get_latest_artifact(project_id, dep)
            if latest is not None:
                conflicts.append(dep)
        return conflicts

    def validate_rollback_target(
        self,
        project_id: str,
        agent_name: str,
        target_identifier: Union[int, str],
        schema_cls: Optional[Type[BaseModel]] = None,
    ) -> Artifact:
        """Validate that a target artifact exists, matches scope, is COMPLETED, and passes schema & security checks."""
        target_artifact: Optional[Artifact] = None

        if isinstance(target_identifier, int):
            target_artifact = self.artifact_manager.get_artifact_version(
                project_id, agent_name, target_identifier
            )
        elif isinstance(target_identifier, str):
            target_artifact = self.artifact_manager.get_artifact(target_identifier)
        else:
            raise RollbackValidationError(
                f"Invalid target identifier type: {type(target_identifier).__name__}"
            )

        if not target_artifact:
            raise RollbackValidationError(
                f"Rollback target '{target_identifier}' not found for project '{project_id}' and agent '{agent_name}'."
            )

        if target_artifact.project_id != project_id:
            raise RollbackValidationError(
                f"Project mismatch: artifact project '{target_artifact.project_id}' does not match '{project_id}'."
            )

        if target_artifact.agent_name != agent_name:
            raise RollbackValidationError(
                f"Agent mismatch: artifact agent '{target_artifact.agent_name}' does not match '{agent_name}'."
            )

        if target_artifact.status != ArtifactStatus.COMPLETED:
            raise RollbackValidationError(
                f"Cannot roll back to artifact '{target_artifact.artifact_id}' with status '{target_artifact.status}'. Target must be COMPLETED."
            )

        try:
            self.artifact_manager.validate_artifact(target_artifact, schema_cls=schema_cls)
        except (ArtifactSecurityError, ArtifactValidationError) as err:
            sanitized_err = sanitize_secret(str(err))
            raise RollbackValidationError(f"Target artifact validation failed: {sanitized_err}") from err

        return target_artifact

    def rollback_to_version(
        self,
        project_id: str,
        agent_name: str,
        target_version: int,
        run_id: Optional[str] = None,
        reason: Optional[str] = None,
        force: bool = False,
        schema_cls: Optional[Type[BaseModel]] = None,
    ) -> RollbackResult:
        """Perform an additive rollback to a target version without destroying artifact history."""
        start_time = time.monotonic()
        eff_run_id = run_id or f"run_rb_{uuid.uuid4().hex[:8]}"
        sanitized_reason = sanitize_secret(reason) if reason else None

        source_artifact = self.artifact_manager.get_latest_artifact(project_id, agent_name)

        self.pipeline_logger.log_rollback_started(
            run_id=eff_run_id,
            project_id=project_id,
            agent_name=agent_name,
            target_version=target_version,
            message=f"Rollback requested for '{agent_name}' to version {target_version}",
        )

        try:
            # Check dependency conflicts
            if not force:
                conflicts = self.check_dependency_conflicts(project_id, agent_name)
                if conflicts and source_artifact:
                    conflict_str = ", ".join(conflicts)
                    raise RollbackDependencyError(
                        f"Cannot rollback agent '{agent_name}': active downstream dependent artifacts exist for [{conflict_str}]. Use force=True to override."
                    )

            # Validate target
            target_artifact = self.validate_rollback_target(
                project_id, agent_name, target_version, schema_cls=schema_cls
            )

            # Build lineage reference
            lineage: List[str] = []
            if source_artifact:
                lineage.append(source_artifact.artifact_id)
            if target_artifact.artifact_id not in lineage:
                lineage.append(target_artifact.artifact_id)

            metadata: Dict[str, Any] = {
                "is_rollback": True,
                "restored_from_version": target_artifact.version,
                "restored_from_artifact_id": target_artifact.artifact_id,
                "source_version": source_artifact.version if source_artifact else None,
                "source_artifact_id": source_artifact.artifact_id if source_artifact else None,
            }
            if sanitized_reason:
                metadata["reason"] = sanitized_reason

            # Additive artifact creation (creates new version, preserving all history)
            restored_artifact = self.artifact_manager.create_artifact(
                project_id=project_id,
                run_id=eff_run_id,
                agent_name=agent_name,
                artifact_type=target_artifact.artifact_type,
                content=target_artifact.content,
                input_artifacts=lineage,
                status=ArtifactStatus.COMPLETED,
                metadata=metadata,
                schema_cls=schema_cls,
            )

            duration_ms = round((time.monotonic() - start_time) * 1000, 2)

            result = RollbackResult(
                project_id=project_id,
                run_id=eff_run_id,
                agent_name=agent_name,
                source_artifact_id=source_artifact.artifact_id if source_artifact else None,
                source_version=source_artifact.version if source_artifact else None,
                target_artifact_id=target_artifact.artifact_id,
                target_version=target_artifact.version,
                restored_artifact_id=restored_artifact.artifact_id,
                restored_version=restored_artifact.version,
                status="COMPLETED",
                reason=sanitized_reason,
            )

            self._history.append(result)

            self.pipeline_logger.log_rollback_completed(
                run_id=eff_run_id,
                project_id=project_id,
                agent_name=agent_name,
                target_version=target_version,
                restored_artifact_id=restored_artifact.artifact_id,
                duration_ms=duration_ms,
            )

            return result

        except Exception as e:
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            sanitized_err = sanitize_secret(str(e))

            failed_result = RollbackResult(
                project_id=project_id,
                run_id=eff_run_id,
                agent_name=agent_name,
                source_artifact_id=source_artifact.artifact_id if source_artifact else None,
                source_version=source_artifact.version if source_artifact else None,
                target_artifact_id=f"version_{target_version}",
                target_version=target_version,
                status="FAILED",
                reason=sanitized_reason,
                error_message=sanitized_err,
            )
            self._history.append(failed_result)

            self.pipeline_logger.log_rollback_failed(
                run_id=eff_run_id,
                project_id=project_id,
                agent_name=agent_name,
                target_version=target_version,
                duration_ms=duration_ms,
                error_type=type(e).__name__,
                error_message=sanitized_err,
            )

            raise e

    def get_rollback_history(
        self, project_id: str, agent_name: Optional[str] = None
    ) -> List[RollbackResult]:
        """Retrieve auditable rollback history for a project and optional agent."""
        results = [r for r in self._history if r.project_id == project_id]
        if agent_name:
            results = [r for r in results if r.agent_name == agent_name]
        return results
