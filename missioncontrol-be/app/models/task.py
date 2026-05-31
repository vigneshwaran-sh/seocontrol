from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class TaskPriority(str, Enum):
    urgent = "urgent"
    high = "high"
    medium = "medium"
    low = "low"
    none = "none"


# --- Task Status models ---

class TaskStatusCreate(BaseModel):
    name: str = Field(min_length=1)
    color: str


class TaskStatusUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    position: Optional[int] = None


class TaskStatusResponse(BaseModel):
    id: str
    space_id: str
    name: str
    color: str
    position: int
    is_default: bool


# --- Task models ---

class TaskCreate(BaseModel):
    title: str = Field(min_length=1)
    status_id: Optional[str] = None
    description: str = ""
    priority: TaskPriority = TaskPriority.none
    assignee_id: Optional[str] = None
    assignee_type: Optional[str] = None  # "user" or "agent"
    due_date: Optional[datetime] = None
    tags: list[str] = []


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    status_id: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    assignee_id: Optional[str] = None
    assignee_type: Optional[str] = None  # "user" or "agent"
    due_date: Optional[datetime] = None
    tags: Optional[list[str]] = None
    position: Optional[int] = None


class TaskMoveRequest(BaseModel):
    status_id: str
    position: int


class TaskResponse(BaseModel):
    id: str
    space_id: str
    status_id: str
    title: str
    description: str
    priority: TaskPriority
    assignee_id: Optional[str] = None
    assignee_type: Optional[str] = None
    due_date: Optional[datetime] = None
    tags: list[str]
    position: int
    revision_count: int = 0
    created_by: str
    created_at: datetime
    updated_at: datetime
