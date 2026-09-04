import os
import json
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.agents.pm_agent import generate_pm_output
from backend.services.pipeline import ForgePipeline, PipelineStage
from backend.artifacts import (
    ArtifactManager,
    LocalJsonArtifactStore,
    RollbackManager,
    RollbackValidationError,
    RollbackDependencyError,
    ArtifactSecurityError,
    ArtifactValidationError,
)
from backend.monitoring import PipelineLogger, MonitoringService, sanitize_secret

app = FastAPI(
    title="Forge AI Backend Server",
    description="FastAPI backend server for Forge AI and Task Management application.",
    version="1.0.0"
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "*",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:[0-9]+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active pipeline runs registry (in-memory)
ACTIVE_PIPELINES: Dict[str, ForgePipeline] = {}

# Exception Handlers
@app.exception_handler(RollbackValidationError)
def rollback_validation_exception_handler(request: Request, exc: RollbackValidationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": sanitize_secret(str(exc))},
    )

@app.exception_handler(RollbackDependencyError)
def rollback_dependency_exception_handler(request: Request, exc: RollbackDependencyError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": sanitize_secret(str(exc))},
    )

@app.exception_handler(ArtifactSecurityError)
def artifact_security_exception_handler(request: Request, exc: ArtifactSecurityError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": sanitize_secret(str(exc))},
    )

@app.exception_handler(ArtifactValidationError)
def artifact_validation_exception_handler(request: Request, exc: ArtifactValidationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": sanitize_secret(str(exc))},
    )

# Database Setup
DB_PATH = Path(__file__).resolve().parent / "tasks.db"

def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        due_date TEXT,
        priority TEXT DEFAULT 'medium',
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

# Initialize DB table on startup
init_db()


# Pydantic Schemas
class PMRequest(BaseModel):
    user_prompt: str = Field(..., example="Build a task management app")

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = "medium"
    status: Optional[str] = "pending"

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None

class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    due_date: Optional[str] = None
    priority: str
    status: str
    created_at: str
    updated_at: str

class ProjectCreateRequest(BaseModel):
    user_prompt: str = Field(..., description="User application prompt/idea")
    project_id: Optional[str] = Field(default=None, description="Optional custom project ID")
    output_dir: Optional[str] = Field(default="outputs", description="Target output directory")
    run_immediately: bool = Field(default=True, description="Whether to execute pipeline immediately")

class RollbackApiRequest(BaseModel):
    agent_name: str = Field(..., description="Stage/agent name to roll back (e.g. pm, ui, backend)")
    target_version: int = Field(..., description="Target artifact version number to restore")
    reason: Optional[str] = Field(default=None, description="Optional reason for rollback")
    force: bool = Field(default=False, description="Force rollback overriding downstream dependencies")


# Endpoints
@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Forge AI Backend Server is running successfully!",
        "docs_url": "/docs"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/api/pm/generate")
def generate_pm_spec(request: PMRequest):
    if not request.user_prompt or not request.user_prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_prompt cannot be empty or whitespace"
        )
    try:
        raw_output = generate_pm_output(request.user_prompt)
        parsed_json = json.loads(raw_output)
        return {"success": True, "data": parsed_json}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_secret(str(e))
        )

# Pipeline & Project API Endpoints
@app.post("/api/projects", status_code=status.HTTP_201_CREATED)
def create_project_run(req: ProjectCreateRequest):
    """Initialize a new ForgePipeline project run and execute if requested."""
    if not req.user_prompt or not req.user_prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_prompt cannot be empty or whitespace"
        )

    if req.project_id and (".." in req.project_id or "/" in req.project_id or "\\" in req.project_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid project_id format '{req.project_id}'"
        )

    if req.output_dir and ".." in req.output_dir:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid output_dir path '{req.output_dir}'"
        )

    pipeline = ForgePipeline(
        user_prompt=req.user_prompt,
        project_id=req.project_id,
        output_dir=req.output_dir or "outputs",
    )
    if req.run_immediately:
        pipeline.run_pipeline()

    key = f"{pipeline.state.project_id}:{pipeline.state.run_id}"
    ACTIVE_PIPELINES[key] = pipeline
    return pipeline.get_status_summary()

@app.get("/api/projects/{project_id}/runs/{run_id}")
def get_run_status(project_id: str, run_id: str):
    """Get status summary for a specific project run."""
    key = f"{project_id}:{run_id}"
    if key in ACTIVE_PIPELINES:
        return ACTIVE_PIPELINES[key].get_status_summary()

    monitoring_svc = MonitoringService()
    events = monitoring_svc.get_events_by_run_id(run_id)
    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found for project '{project_id}'"
        )
    metrics = monitoring_svc.get_execution_metrics(run_id=run_id, project_id=project_id)
    return {
        "project_id": project_id,
        "run_id": run_id,
        "execution_status": metrics.get("pipeline_status", "UNKNOWN"),
        "metrics": metrics,
    }

@app.get("/api/projects/{project_id}/runs/{run_id}/artifacts")
def get_run_artifacts(project_id: str, run_id: str):
    """Get all stored artifacts for a specific project run."""
    key = f"{project_id}:{run_id}"
    if key in ACTIVE_PIPELINES:
        art_mgr = ACTIVE_PIPELINES[key].artifact_manager
    else:
        art_mgr = ArtifactManager()

    artifacts = art_mgr.list_artifacts(project_id=project_id, run_id=run_id)
    if not artifacts and key not in ACTIVE_PIPELINES:
        events = MonitoringService().get_events_by_run_id(run_id)
        if not events:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' not found for project '{project_id}'"
            )
    return {
        "project_id": project_id,
        "run_id": run_id,
        "count": len(artifacts),
        "artifacts": [a.model_dump() for a in artifacts],
    }

@app.get("/api/artifacts/{artifact_id}")
def get_artifact_by_id(artifact_id: str):
    """Retrieve a specific artifact by artifact_id."""
    for pipeline in ACTIVE_PIPELINES.values():
        art = pipeline.artifact_manager.get_artifact(artifact_id)
        if art:
            return art.model_dump()

    default_mgr = ArtifactManager()
    art = default_mgr.get_artifact(artifact_id)
    if art:
        return art.model_dump()

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Artifact '{artifact_id}' not found"
    )

@app.get("/api/projects/{project_id}/runs/{run_id}/events")
def get_run_events(project_id: str, run_id: str):
    """Get monitoring execution events for a specific run."""
    key = f"{project_id}:{run_id}"
    if key in ACTIVE_PIPELINES:
        svc = ACTIVE_PIPELINES[key].monitoring_service
    else:
        svc = MonitoringService()

    events = svc.get_events_by_run_id(run_id)
    if not events and key not in ACTIVE_PIPELINES:
        artifacts = ArtifactManager().list_artifacts(project_id=project_id, run_id=run_id)
        if not artifacts:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' not found for project '{project_id}'"
            )
    return {
        "project_id": project_id,
        "run_id": run_id,
        "count": len(events),
        "events": [e.model_dump() for e in events],
    }

@app.post("/api/projects/{project_id}/runs/{run_id}/rollback")
def rollback_run_stage(project_id: str, run_id: str, req: RollbackApiRequest):
    """Roll back a specific stage/agent artifact to a target version."""
    key = f"{project_id}:{run_id}"
    if key in ACTIVE_PIPELINES:
        pipeline = ACTIVE_PIPELINES[key]
        try:
            stage_enum = PipelineStage(req.agent_name.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid pipeline stage/agent name '{req.agent_name}'"
            )

        result = pipeline.rollback_stage(
            stage=stage_enum,
            target_version=req.target_version,
            reason=req.reason,
            force=req.force,
        )
        return result.model_dump()
    else:
        art_mgr = ArtifactManager()
        rollback_mgr = RollbackManager(artifact_manager=art_mgr)
        result = rollback_mgr.rollback_to_version(
            project_id=project_id,
            agent_name=req.agent_name,
            target_version=req.target_version,
            run_id=run_id,
            reason=req.reason,
            force=req.force,
        )
        return result.model_dump()


# Task CRUD Endpoints
@app.get("/api/tasks", response_model=List[TaskResponse])
def get_tasks(status_filter: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if status_filter:
        cursor.execute("SELECT * FROM tasks WHERE status = ? ORDER BY id DESC", (status_filter,))
    else:
        cursor.execute("SELECT * FROM tasks ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found")
    return dict(row)

@app.post("/api/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(task: TaskCreate):
    now = datetime.now().isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks (title, description, due_date, priority, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (task.title, task.description, task.due_date, task.priority or "medium", task.status or "pending", now, now)
    )
    conn.commit()
    task_id = cursor.lastrowid
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)

@app.put("/api/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, task_update: TaskUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found")
    
    current = dict(row)
    title = task_update.title if task_update.title is not None else current["title"]
    description = task_update.description if task_update.description is not None else current["description"]
    due_date = task_update.due_date if task_update.due_date is not None else current["due_date"]
    priority = task_update.priority if task_update.priority is not None else current["priority"]
    task_status = task_update.status if task_update.status is not None else current["status"]
    now = datetime.now().isoformat()

    cursor.execute(
        """
        UPDATE tasks
        SET title = ?, description = ?, due_date = ?, priority = ?, status = ?, updated_at = ?
        WHERE id = ?
        """,
        (title, description, due_date, priority, task_status, now, task_id)
    )
    conn.commit()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    updated_row = cursor.fetchone()
    conn.close()
    return dict(updated_row)

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found")
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return {"message": f"Task {task_id} deleted successfully"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
