"""Minimal compatibility stub schema for BackendOutput."""

from typing import List, Any
from pydantic import BaseModel, Field


class BackendOutput(BaseModel):
    project_name: str
    endpoints: List[Any] = Field(default_factory=list)
    service_layer: List[Any] = Field(default_factory=list)
    repository_layer: List[Any] = Field(default_factory=list)
