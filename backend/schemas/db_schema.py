"""Minimal compatibility stub schema for DBOutput."""

from typing import List, Any, Optional
from pydantic import BaseModel, Field


class AlembicMetadata(BaseModel):
    revision_id: str = "rev_001"


class DBOutput(BaseModel):
    project_name: str
    database_system: str = "PostgreSQL"
    tables: List[Any] = Field(default_factory=list)
    sqlalchemy_models_code: str = "Base = declarative_base()\nclass User(Base):\n    pass\nclass Post(Base):\n    pass"
    alembic_metadata: AlembicMetadata = Field(default_factory=AlembicMetadata)
