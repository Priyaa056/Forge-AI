"""PM schema for FORGE AI Multi-Agent System."""

from typing import List
from pydantic import BaseModel, Field


class DatabaseField(BaseModel):
    name: str
    type: str
    nullable: bool = False
    unique: bool = False
    primary_key: bool = False

class DatabaseEntity(BaseModel):
    name: str
    fields: List[DatabaseField] = Field(default_factory=list)


class TechStack(BaseModel):
    frontend: str = "React"
    backend: str = "FastAPI"
    database: str = "PostgreSQL"


class PMOutput(BaseModel):
    project_name: str
    description: str = ""
    features: List[str] = Field(default_factory=list)
    tech_stack: TechStack = Field(default_factory=TechStack)
    database_entities: List[DatabaseEntity] = Field(default_factory=list)
