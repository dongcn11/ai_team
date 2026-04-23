from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class TaskCreate(BaseModel):
    role: str
    description: Optional[str] = None


class TaskUpdate(BaseModel):
    run_id: int
    role: str
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_s: Optional[int] = None
    error: Optional[str] = None


class TaskOut(BaseModel):
    id: int
    run_id: int
    role: str
    description: Optional[str]
    status: str
    started_at: Optional[str]
    finished_at: Optional[str]
    duration_s: Optional[int]
    error: Optional[str]

    model_config = {"from_attributes": True}


class IssueCreate(BaseModel):
    run_id: int
    role: str
    severity: str = "medium"
    description: Optional[str] = None
    suggestion: Optional[str] = None


class IssueOut(BaseModel):
    id: int
    run_id: int
    role: str
    severity: str
    description: Optional[str]
    suggestion: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class RunCreate(BaseModel):
    client: Optional[str] = None
    profile: Optional[str] = None
    tasks: List[TaskCreate] = []


class RunOut(BaseModel):
    id: int
    client: Optional[str]
    profile: Optional[str]
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    tasks: List[TaskOut] = []
    issues: List[IssueOut] = []

    model_config = {"from_attributes": True}


class RunSummary(BaseModel):
    id: int
    client: Optional[str]
    profile: Optional[str]
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    total_tasks: int
    done_tasks: int
    failed_tasks: int

    model_config = {"from_attributes": True}
