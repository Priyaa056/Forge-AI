"""Structured Pipeline Logger implementation with machine-readable file sink and secret sanitization."""

import json
import re
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from backend.monitoring.execution_event import ExecutionEvent, EventType

logger = logging.getLogger("pipeline_logger")

SPECIFIC_SECRET_PATTERNS = [
    # Specific API Key / Token Formats
    (re.compile(r"AIzaSy[a-zA-Z0-9_-]{20,}"), "[REDACTED_GEMINI_KEY]"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]+"), "Bearer [REDACTED_TOKEN]"),
]

KV_CREDENTIAL_PATTERN = re.compile(
    r"(?i)\b([a-z0-9_\-]*?(?:key|secret|password|passwd|token|jwt|auth|credential)[a-z0-9_\-]*?)\s*[:=]\s*(['\"]?)([^\s'\":;,]+)(['\"]?)"
)

DB_URI_PATTERN = (re.compile(r"(?i)([a-z0-9\+\.-]+://[^:\s]+):([^@\s]+)@"), r"\1:[REDACTED]@")


def _redact_kv_match(match: re.Match) -> str:
    """Helper callback to redact key-value credentials while preserving already redacted tags."""
    key = match.group(1)
    quote1 = match.group(2)
    val = match.group(3)
    quote2 = match.group(4)
    if val.startswith("[REDACTED"):
        return match.group(0)
    return f"{key}={quote1}[REDACTED]{quote2}"


def sanitize_secret(text: Optional[str]) -> Optional[str]:
    """Sanitize sensitive credentials, API keys, passwords, and tokens from log strings."""
    if not text:
        return text
    sanitized = text

    # 1. Sanitize known specific token formats
    for pattern, replacement in SPECIFIC_SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    # 2. Sanitize key-value credential assignments (preserving already redacted tags)
    sanitized = KV_CREDENTIAL_PATTERN.sub(_redact_kv_match, sanitized)

    # 3. Sanitize DB connection URIs
    sanitized = DB_URI_PATTERN[0].sub(DB_URI_PATTERN[1], sanitized)

    return sanitized


class PipelineLogger:
    """Structured event logger with local machine-readable JSON Lines file sink."""

    def __init__(
        self,
        log_dir: Optional[str] = None,
        log_filename: str = "pipeline_execution.jsonl",
    ):
        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            self.log_dir = Path("backend/data/logs")

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_filepath = self.log_dir / log_filename
        self._events: List[ExecutionEvent] = []

    def log_event(self, event: ExecutionEvent) -> ExecutionEvent:
        """Sanitize, persist to JSON Lines sink, and record execution event."""
        # Sanitize text fields
        if event.message:
            event.message = sanitize_secret(event.message)
        if event.error_message:
            event.error_message = sanitize_secret(event.error_message)

        self._events.append(event)

        # Write machine-readable JSON record
        try:
            with open(self.log_filepath, "a", encoding="utf-8") as f:
                f.write(event.model_dump_json() + "\n")
        except Exception as e:
            logger.error(f"Failed to write execution log event: {e}")

        return event

    def log_pipeline_started(
        self,
        run_id: str,
        project_id: str,
        message: Optional[str] = None,
    ) -> ExecutionEvent:
        event = ExecutionEvent(
            run_id=run_id,
            project_id=project_id,
            event_type=EventType.PIPELINE_STARTED,
            status="RUNNING",
            message=message or f"Pipeline execution started for run {run_id}",
        )
        return self.log_event(event)

    def log_pipeline_completed(
        self,
        run_id: str,
        project_id: str,
        duration_ms: float,
        message: Optional[str] = None,
    ) -> ExecutionEvent:
        event = ExecutionEvent(
            run_id=run_id,
            project_id=project_id,
            event_type=EventType.PIPELINE_COMPLETED,
            status="COMPLETED",
            duration_ms=duration_ms,
            message=message or f"Pipeline execution completed in {duration_ms}ms",
        )
        return self.log_event(event)

    def log_pipeline_failed(
        self,
        run_id: str,
        project_id: str,
        duration_ms: float,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> ExecutionEvent:
        event = ExecutionEvent(
            run_id=run_id,
            project_id=project_id,
            event_type=EventType.PIPELINE_FAILED,
            status="FAILED",
            duration_ms=duration_ms,
            error_type=error_type,
            error_message=error_message,
            message=f"Pipeline execution failed after {duration_ms}ms: {error_message}",
        )
        return self.log_event(event)

    def log_agent_started(
        self,
        run_id: str,
        project_id: str,
        agent_name: str,
        pipeline_stage: str,
    ) -> ExecutionEvent:
        event = ExecutionEvent(
            run_id=run_id,
            project_id=project_id,
            event_type=EventType.AGENT_STARTED,
            agent_name=agent_name,
            pipeline_stage=pipeline_stage,
            status="RUNNING",
            message=f"Agent '{agent_name}' started stage '{pipeline_stage}'",
        )
        return self.log_event(event)

    def log_agent_completed(
        self,
        run_id: str,
        project_id: str,
        agent_name: str,
        pipeline_stage: str,
        duration_ms: float,
        artifact_id: Optional[str] = None,
        input_artifact_ids: Optional[List[str]] = None,
    ) -> ExecutionEvent:
        event = ExecutionEvent(
            run_id=run_id,
            project_id=project_id,
            event_type=EventType.AGENT_COMPLETED,
            agent_name=agent_name,
            pipeline_stage=pipeline_stage,
            status="COMPLETED",
            duration_ms=duration_ms,
            artifact_id=artifact_id,
            input_artifact_ids=input_artifact_ids or [],
            message=f"Agent '{agent_name}' completed stage '{pipeline_stage}' in {duration_ms}ms",
        )
        return self.log_event(event)

    def log_agent_failed(
        self,
        run_id: str,
        project_id: str,
        agent_name: str,
        pipeline_stage: str,
        duration_ms: float,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        artifact_id: Optional[str] = None,
        input_artifact_ids: Optional[List[str]] = None,
    ) -> ExecutionEvent:
        event = ExecutionEvent(
            run_id=run_id,
            project_id=project_id,
            event_type=EventType.AGENT_FAILED,
            agent_name=agent_name,
            pipeline_stage=pipeline_stage,
            status="FAILED",
            duration_ms=duration_ms,
            artifact_id=artifact_id,
            input_artifact_ids=input_artifact_ids or [],
            error_type=error_type,
            error_message=error_message,
            message=f"Agent '{agent_name}' failed stage '{pipeline_stage}' after {duration_ms}ms: {error_message}",
        )
        return self.log_event(event)

    def log_artifact_created(
        self,
        run_id: str,
        project_id: str,
        agent_name: str,
        pipeline_stage: str,
        artifact_id: str,
        input_artifact_ids: Optional[List[str]] = None,
    ) -> ExecutionEvent:
        event = ExecutionEvent(
            run_id=run_id,
            project_id=project_id,
            event_type=EventType.ARTIFACT_CREATED,
            agent_name=agent_name,
            pipeline_stage=pipeline_stage,
            status="COMPLETED",
            artifact_id=artifact_id,
            input_artifact_ids=input_artifact_ids or [],
            message=f"Artifact '{artifact_id}' created for agent '{agent_name}'",
        )
        return self.log_event(event)

    def log_artifact_failed(
        self,
        run_id: str,
        project_id: str,
        agent_name: str,
        pipeline_stage: str,
        artifact_id: Optional[str] = None,
        input_artifact_ids: Optional[List[str]] = None,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> ExecutionEvent:
        event = ExecutionEvent(
            run_id=run_id,
            project_id=project_id,
            event_type=EventType.ARTIFACT_FAILED,
            agent_name=agent_name,
            pipeline_stage=pipeline_stage,
            status="FAILED",
            artifact_id=artifact_id,
            input_artifact_ids=input_artifact_ids or [],
            error_type=error_type,
            error_message=error_message,
            message=f"Artifact creation failed for agent '{agent_name}'",
        )
        return self.log_event(event)

    def log_rollback_started(
        self,
        run_id: str,
        project_id: str,
        agent_name: str,
        target_version: int,
        message: Optional[str] = None,
    ) -> ExecutionEvent:
        event = ExecutionEvent(
            run_id=run_id,
            project_id=project_id,
            event_type=EventType.ROLLBACK_STARTED,
            agent_name=agent_name,
            pipeline_stage=agent_name,
            status="RUNNING",
            message=message or f"Rollback started for agent '{agent_name}' to version {target_version}",
        )
        return self.log_event(event)

    def log_rollback_completed(
        self,
        run_id: str,
        project_id: str,
        agent_name: str,
        target_version: int,
        restored_artifact_id: str,
        duration_ms: float,
        message: Optional[str] = None,
    ) -> ExecutionEvent:
        event = ExecutionEvent(
            run_id=run_id,
            project_id=project_id,
            event_type=EventType.ROLLBACK_COMPLETED,
            agent_name=agent_name,
            pipeline_stage=agent_name,
            status="COMPLETED",
            duration_ms=duration_ms,
            artifact_id=restored_artifact_id,
            message=message or f"Rollback completed for agent '{agent_name}' to version {target_version} in {duration_ms}ms",
        )
        return self.log_event(event)

    def log_rollback_failed(
        self,
        run_id: str,
        project_id: str,
        agent_name: str,
        target_version: int,
        duration_ms: float,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> ExecutionEvent:
        event = ExecutionEvent(
            run_id=run_id,
            project_id=project_id,
            event_type=EventType.ROLLBACK_FAILED,
            agent_name=agent_name,
            pipeline_stage=agent_name,
            status="FAILED",
            duration_ms=duration_ms,
            error_type=error_type,
            error_message=error_message,
            message=f"Rollback failed for agent '{agent_name}' to version {target_version}: {error_message}",
        )
        return self.log_event(event)

    def get_events(self, run_id: Optional[str] = None) -> List[ExecutionEvent]:
        """Return in-memory execution events, optionally filtered by run_id."""
        if run_id:
            return [evt for evt in self._events if evt.run_id == run_id]
        return list(self._events)

    def read_logs_from_file(self) -> List[ExecutionEvent]:
        """Read and parse all execution events from persistent JSON Lines file."""
        events: List[ExecutionEvent] = []
        if not self.log_filepath.exists():
            return events

        with open(self.log_filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    events.append(ExecutionEvent.model_validate(data))
                except Exception as e:
                    logger.error(f"Failed to parse log line: {e}")
        return events

    def get_query_service(self):
        """Return a MonitoringService instance linked to this logger."""
        from backend.monitoring.query import MonitoringService
        return MonitoringService(logger_instance=self)

    def get_events_by_project_id(self, project_id: str) -> List[ExecutionEvent]:
        """Retrieve events filtered by project_id."""
        return self.get_query_service().get_events_by_project_id(project_id)

    def get_events_by_agent(self, agent_name: str, run_id: Optional[str] = None) -> List[ExecutionEvent]:
        """Retrieve events filtered by agent_name."""
        return self.get_query_service().get_events_by_agent(agent_name, run_id=run_id)

    def get_failed_events(self, run_id: Optional[str] = None, project_id: Optional[str] = None) -> List[ExecutionEvent]:
        """Retrieve failed execution events."""
        return self.get_query_service().get_failed_events(run_id=run_id, project_id=project_id)

    def get_events_by_stage(self, pipeline_stage: str, run_id: Optional[str] = None) -> List[ExecutionEvent]:
        """Retrieve events filtered by pipeline stage."""
        return self.get_query_service().get_events_by_stage(pipeline_stage, run_id=run_id)

    def get_metrics(self, run_id: Optional[str] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
        """Calculate execution metrics for a specific run or project."""
        return self.get_query_service().get_execution_metrics(run_id=run_id, project_id=project_id)

