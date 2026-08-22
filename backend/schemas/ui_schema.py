"""Pydantic schemas for UIAgent and frontend output specification."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class UIPage(BaseModel):
    name: str
    route_path: str
    layout: str = "MainLayout"
    description: str = ""
    components_used: List[str] = Field(default_factory=list)
    required_auth: bool = False
    state_requirements: List[str] = Field(default_factory=list)


class UIComponent(BaseModel):
    name: str
    type: str
    description: str = ""
    props: List[Dict[str, Any]] = Field(default_factory=list)
    state_variables: List[Dict[str, Any]] = Field(default_factory=list)
    event_handlers: List[str] = Field(default_factory=list)
    child_components: List[str] = Field(default_factory=list)


class UIRoute(BaseModel):
    path: str
    component_name: str
    exact: bool = True
    protected: bool = False
    title: str = ""


class UILayout(BaseModel):
    name: str
    description: str = ""
    slots: List[str] = Field(default_factory=lambda: ["main"])
    default_layout: bool = True


class UIForm(BaseModel):
    name: str = ""
    form_name: Optional[str] = None
    entity_name: str = ""
    fields: List[Dict[str, Any]] = Field(default_factory=list)
    submit_endpoint: str = ""
    validation_rules: List[Any] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if not self.name and self.form_name:
            self.name = self.form_name


class FrontendDependency(BaseModel):
    package_name: str
    version: str
    purpose: str = ""
    category: str = "core"


class APIRequirement(BaseModel):
    endpoint: str
    method: str
    description: str = ""
    request_body: Optional[Dict[str, Any]] = None
    response_schema: Optional[Dict[str, Any]] = None


class StylingRequirements(BaseModel):
    theme_mode: str = "dark"
    primary_color: str = "#6366F1"
    font_family: str = "Inter, sans-serif"
    design_system_notes: str = "Modern clean UI"
    css_approach: str = "Vanilla CSS"


class UIOutput(BaseModel):
    project_name: str
    pages: List[UIPage] = Field(default_factory=list)
    components: List[UIComponent] = Field(default_factory=list)
    routes: List[UIRoute] = Field(default_factory=list)
    layouts: List[UILayout] = Field(default_factory=list)
    forms: List[UIForm] = Field(default_factory=list)
    frontend_dependencies: List[FrontendDependency] = Field(default_factory=list)
    api_requirements: List[APIRequirement] = Field(default_factory=list)
    styling_requirements: StylingRequirements = Field(default_factory=StylingRequirements)
