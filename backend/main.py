import os
import json
import sqlite3
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.agents.pm_agent import generate_pm_output

app = FastAPI(
    title="Forge AI Backend Server",
    description="FastAPI backend server for Forge AI and Task Management application.",
    version="1.0.0"
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    try:
        raw_output = generate_pm_output(request.user_prompt)
        parsed_json = json.loads(raw_output)
        return {"success": True, "data": parsed_json}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

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
