"""Pydantic V2 schemas for the PM Agent output (``requirements.json``).

Backwards compatible with the original PM contract (project_name, description, features,
tech_stack, database_entities); the additional fields carry the structured requirements that
downstream agents consume.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

FIELD_TYPES = [
    "string", "text", "integer", "float", "decimal", "boolean", "date", "datetime", "time", "email", "enum", "reference",
]


class EntityField(BaseModel):
    """Field definition in a database entity."""
    name: str = Field(..., description="Field name (snake_case)")
    type: str = Field(..., description="Semantic type: " + ", ".join(FIELD_TYPES) + " (legacy SQL types are accepted)")
    nullable: Optional[bool] = Field(default=True, description="Whether field can be NULL")
    primary_key: Optional[bool] = Field(default=False, description="Whether field is primary key")
    unique: Optional[bool] = Field(default=False, description="Whether field is unique")
    description: Optional[str] = Field(default=None, description="Field description")
    label: Optional[str] = Field(default=None, description="Human readable label for forms and tables")
    enum_values: List[str] = Field(default_factory=list, description="Allowed values for enum fields")
    references: Optional[str] = Field(default=None, description="Target entity for reference (foreign key) fields")
    read_only: bool = Field(default=False, description="Set by the system, never by API clients (id, created_at, owner_id)")
    hidden: bool = Field(default=False, description="Never returned by the API (e.g. hashed_password)")
    searchable: bool = Field(default=False, description="Included in free-text search")
    min_value: Optional[float] = Field(default=None, description="Minimum numeric value")
    max_value: Optional[float] = Field(default=None, description="Maximum numeric value")
    default: Optional[str] = Field(default=None, description="Default value")


class DatabaseEntity(BaseModel):
    """Domain entity identified by the PM agent."""
    name: str = Field(..., description="Entity name in PascalCase e.g. User, Task")
    description: Optional[str] = Field(default=None, description="Entity description")
    fields: List[EntityField] = Field(default_factory=list, description="Fields belonging to entity")
    access: str = Field(
        default="owner",
        description="Access policy: 'owner' (users manage their own records, admins see all), "
        "'admin_managed' (admins write, signed-in users read), 'shared' (all signed-in users read/write)",
    )
    display_field: Optional[str] = Field(default=None, description="Field used to label records in dropdowns")
    is_system: bool = Field(default=False, description="True for the platform-managed User entity")


class TechStack(BaseModel):
    """Tech stack choice."""
    frontend: Optional[str] = Field(default="React", description="Frontend framework")
    backend: Optional[str] = Field(default="FastAPI", description="Backend framework")
    database: Optional[str] = Field(default="PostgreSQL", description="Database system")


class UserRole(BaseModel):
    name: str = Field(..., description="Role identifier e.g. admin, user")
    description: str = Field(default="", description="Role responsibilities")
    is_admin: bool = Field(default=False, description="Role has full administrative access")


class Requirement(BaseModel):
    id: str = Field(..., description="Requirement identifier e.g. FR-001")
    title: str
    description: str = ""
    priority: str = Field(default="must", description="must | should | could")
    module: Optional[str] = None


class DevelopmentTask(BaseModel):
    step: int
    agent: str = Field(..., description="Responsible agent: pm, ui, backend, db, auth, qa, deploy")
    description: str
    depends_on: List[str] = Field(default_factory=list)


class ModuleSpec(BaseModel):
    """A module the user asked for, as it appears in navigation."""
    key: str = Field(..., description="snake_case identifier")
    name: str = Field(..., description="Name in the user's terminology e.g. 'Admission and Bed Management'")
    label: str = Field(..., description="Short navigation label e.g. 'Admissions & Beds'")
    kind: str = Field(default="entities", description="entities | dashboard | reports")
    entities: List[str] = Field(default_factory=list, description="Entities managed on this module's page")
    description: str = ""
    source: str = Field(default="", description="Prompt text this module was derived from")


class WorkflowTransition(BaseModel):
    action: str = Field(..., description="snake_case action e.g. discharge")
    label: str = Field(..., description="Button label e.g. 'Discharge'")
    from_states: List[str] = Field(default_factory=list)
    to_state: str


class WorkflowSpec(BaseModel):
    entity: str
    field: str = "status"
    states: List[str]
    initial: str
    terminal: List[str] = Field(default_factory=list)
    transitions: List[WorkflowTransition] = Field(default_factory=list)
    source: str = ""


class BusinessRule(BaseModel):
    id: str
    kind: str = Field(..., description="unique_together | date_order | allocation | computed | low_stock | expiry | overdue")
    entity: str
    fields: List[str] = Field(default_factory=list)
    params: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    source: str = ""


class DashboardMetric(BaseModel):
    id: str
    label: str
    kind: str = Field(..., description="count | count_where | count_today | upcoming | sum | sum_month | average | alert | breakdown | trend | recent")
    entity: Optional[str] = None
    field: Optional[str] = None
    value: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class RolePermission(BaseModel):
    role: str
    entity: str
    actions: List[str] = Field(default_factory=list, description="read | create | update | delete")


class TraceItem(BaseModel):
    """Traceability from a prompt requirement to the specification items that implement it."""
    id: str
    text: str
    kind: str = Field(..., description="module | entity | field | role | workflow | rule | metric | page | feature")
    targets: List[str] = Field(default_factory=list)
    status: str = Field(default="mapped", description="mapped | unsupported")


class PMOutput(BaseModel):
    """PM Agent JSON output schema (requirements.json)."""
    project_name: str = Field(..., description="Project name")
    description: str = Field(..., description="Project summary description")
    features: List[str] = Field(default_factory=list, description="Core feature list")
    tech_stack: Optional[TechStack] = Field(default_factory=TechStack, description="Target tech stack")
    database_entities: List[DatabaseEntity] = Field(default_factory=list, description="Extracted database entities")

    app_type: str = Field(default="custom", description="Detected application domain e.g. task_management, ecommerce")
    modules: List[str] = Field(default_factory=list, description="Application modules")
    user_roles: List[UserRole] = Field(default_factory=list, description="User roles")
    functional_requirements: List[Requirement] = Field(default_factory=list)
    non_functional_requirements: List[Requirement] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list, description="Dependencies between modules/entities")
    development_plan: List[DevelopmentTask] = Field(default_factory=list)
    requires_auth: bool = Field(default=True)
    has_admin_dashboard: bool = Field(default=True)
    source_prompt: str = Field(default="", description="The user prompt these requirements were derived from")
    generation_mode: str = Field(default="deterministic", description="'llm' or 'deterministic'")
    assumptions: List[str] = Field(default_factory=list, description="Assumptions made while interpreting the prompt")

    # Dynamic application specification (derived from the prompt; consumed by every agent)
    purpose: str = Field(default="", description="One-sentence purpose of the application")
    target_users: List[str] = Field(default_factory=list)
    module_specs: List[ModuleSpec] = Field(default_factory=list, description="Modules/pages in prompt order")
    workflows: List[WorkflowSpec] = Field(default_factory=list)
    business_rules: List[BusinessRule] = Field(default_factory=list)
    dashboard_metrics: List[DashboardMetric] = Field(default_factory=list)
    role_permissions: List[RolePermission] = Field(default_factory=list)
    ambiguities: List[str] = Field(default_factory=list, description="Missing or ambiguous requirements and how they were resolved")
    unsupported_requests: List[str] = Field(default_factory=list, description="Requested capabilities FORGE AI cannot generate")
    theme: Dict[str, str] = Field(default_factory=dict, description="primary_color, sidebar_color, style notes")
    seed_records: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict, description="Records the prompt explicitly listed")
    demo_data: bool = Field(default=False, description="The prompt asked for sample/demo data")
    requirement_trace: List[TraceItem] = Field(default_factory=list)
    spec_version: int = Field(default=2)
