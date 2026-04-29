from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from models.task import TaskStatus, TaskPriority
import uuid


class TaskCreate(SQLModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    deadline: Optional[datetime] = None


class TaskUpdate(SQLModel):
    title: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    priority: Optional[TaskPriority] = None
    deadline: Optional[datetime] = None


class TaskStatusUpdate(SQLModel):
    status: TaskStatus


class TaskResponse(SQLModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: Optional[str]
    status: TaskStatus
    priority: TaskPriority
    deadline: Optional[datetime]
    created_at: datetime
    updated_at: datetime
