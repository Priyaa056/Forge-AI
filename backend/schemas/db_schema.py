"""Pydantic V2 schemas for Database Agent Output validation."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ForeignKeySpec(BaseModel):
    """Foreign key constraint specification."""
    target_table: str = Field(..., description="Target table referenced by foreign key")
    target_column: str = Field(..., description="Target column referenced in target table")
    on_delete: str = Field(default="CASCADE", description="ON DELETE action e.g. CASCADE, SET NULL, RESTRICT")
    on_update: str = Field(default="CASCADE", description="ON UPDATE action")


class ColumnSpec(BaseModel):
    """PostgreSQL / SQLAlchemy column specification."""
    name: str = Field(..., description="Column name")
    data_type: str = Field(..., description="PostgreSQL data type e.g. INTEGER, VARCHAR(255), TIMESTAMP WITH TIME ZONE")
    is_primary_key: bool = Field(default=False, description="Is primary key")
    is_nullable: bool = Field(default=True, description="Is column nullable")
    is_unique: bool = Field(default=False, description="Is column unique constraint")
    default_value: Optional[str] = Field(default=None, description="Default SQL expression e.g. now(), autoincrement")
    foreign_key: Optional[ForeignKeySpec] = Field(default=None, description="Foreign key specification if applicable")
    check_constraint: Optional[str] = Field(default=None, description="SQL CHECK constraint expression")


class RelationshipSpec(BaseModel):
    """SQLAlchemy ORM Relationship specification (1:N, N:1, N:M)."""
    relationship_name: str = Field(..., description="Python property name e.g. tasks, user, categories")
    type: str = Field(..., description="Relationship type: 'one-to-many', 'many-to-one', 'many-to-many'")
    target_model: str = Field(..., description="Target SQLAlchemy model class name e.g. Task")
    back_populates: Optional[str] = Field(default=None, description="Back populates attribute name on target model")
    secondary_table: Optional[str] = Field(default=None, description="Association table name for many-to-many relationship")
    cascade: Optional[str] = Field(default="all, delete-orphan", description="Cascade rules")


class IndexSpec(BaseModel):
    """Database index specification."""
    name: str = Field(..., description="Index name e.g. idx_tasks_user_id")
    table_name: str = Field(..., description="Target table name")
    columns: List[str] = Field(..., description="List of columns included in index")
    is_unique: bool = Field(default=False, description="Whether index enforces uniqueness")
    index_type: str = Field(default="btree", description="PostgreSQL index type e.g. btree, hash, gin")


class TableSpec(BaseModel):
    """Database table specification."""
    table_name: str = Field(..., description="SQL table name e.g. users, tasks")
    model_name: str = Field(..., description="SQLAlchemy model class name e.g. User, Task")
    columns: List[ColumnSpec] = Field(default_factory=list, description="List of table columns")
    relationships: List[RelationshipSpec] = Field(default_factory=list, description="List of SQLAlchemy relationships")
    indexes: List[IndexSpec] = Field(default_factory=list, description="List of indexes defined on table")
    is_association_table: bool = Field(default=False, description="Whether table is a many-to-many junction table")


class AlembicMetadata(BaseModel):
    """Alembic migration generation metadata."""
    revision_id: str = Field(..., description="Revision hash")
    down_revision: Optional[str] = Field(default=None, description="Parent revision hash")
    description: str = Field(..., description="Migration message e.g. Create initial schema")
    upgrade_instructions: List[str] = Field(default_factory=list, description="List of DDL upgrade operations")
    downgrade_instructions: List[str] = Field(default_factory=list, description="List of DDL downgrade operations")


class DBOutput(BaseModel):
    """Database Agent JSON output schema."""
    project_name: str = Field(..., description="Project name")
    database_system: str = Field(default="PostgreSQL", description="Target DBMS")
    tables: List[TableSpec] = Field(default_factory=list, description="All database tables")
    sqlalchemy_models_code: str = Field(..., description="Generated Python code string containing SQLAlchemy 2.x ORM models")
    alembic_metadata: AlembicMetadata = Field(..., description="Alembic migration details")
