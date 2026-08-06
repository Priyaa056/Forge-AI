"""Pydantic V2 schemas for UI Agent Output validation."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class UIComponentSpec(BaseModel):
    """Specification for an individual UI Component."""
    name: str = Field(..., description="Component name e.g. Navbar, TaskCard, Sidebar")
    description: Optional[str] = Field(default=None, description="Component purpose")
    props: List[Dict[str, str]] = Field(default_factory=list, description="Props accepted by component")


class PageComponentSpec(BaseModel):
    """Specification for a top-level page in the UI application."""
    name: str = Field(..., description="Page name e.g. Home, Dashboard, Login")
    path: str = Field(..., description="Route path e.g. /dashboard")
    components: List[str] = Field(default_factory=list, description="Child component names used in page")
    description: Optional[str] = Field(default=None, description="Page description")


class UIOutput(BaseModel):
    """UI Agent JSON output schema."""
    project_name: str = Field(..., description="Project name")
    framework: str = Field(default="React", description="Frontend framework e.g. React, Next.js")
    styling: str = Field(default="Tailwind CSS", description="Styling framework e.g. Tailwind CSS, Vanilla CSS")
    pages: List[PageComponentSpec] = Field(default_factory=list, description="Pages defined in UI")
    components: List[UIComponentSpec] = Field(default_factory=list, description="Reusable components")
    design_system: Dict[str, Any] = Field(default_factory=dict, description="Design tokens e.g. colors, typography")
    routes: List[Dict[str, str]] = Field(default_factory=list, description="Routing configuration")
    code_files: Dict[str, str] = Field(default_factory=dict, description="Generated code files mapping path to code")
