"""Services package for FORGE AI (pipeline orchestration, runs, projects, previews, failure classification,
self-healing).

The pipeline is imported lazily: agents import services such as ``backend.services.failure_classifier``,
and eagerly importing the pipeline here would create a circular import.
"""

__all__ = ["ForgePipeline", "AgentStatus", "PipelineStage", "PipelineExecutionState"]


def __getattr__(name):
    if name in __all__:
        from backend.services import pipeline

        return getattr(pipeline, name)
    raise AttributeError(f"module 'backend.services' has no attribute {name!r}")
