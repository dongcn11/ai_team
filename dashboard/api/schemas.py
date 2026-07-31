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
    project_id: Optional[int] = None
    tasks: List[TaskCreate] = []


class RunOut(BaseModel):
    id: int
    project_id: Optional[int]
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
    project_id: Optional[int]
    client: Optional[str]
    profile: Optional[str]
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    total_tasks: int
    done_tasks: int
    failed_tasks: int

    model_config = {"from_attributes": True}


class RunJobCreate(BaseModel):
    client_folder: str
    profile: Optional[str] = None


class RunJobComplete(BaseModel):
    status: str                    # done / failed
    error: Optional[str] = None


class RunJobOut(BaseModel):
    id: int
    client_folder: str
    project_id: Optional[int]
    profile: Optional[str]
    feature_ids: Optional[str]
    status: str
    run_id: Optional[int]
    error: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ── Workflow ──

class WorkflowGraphIn(BaseModel):
    """Graph thô. Validate bằng ai_team.workflow.graph.validate() trước khi lưu."""
    name: Optional[str] = None
    nodes: List[dict] = []
    edges: List[dict] = []


class WorkflowValidateOut(BaseModel):
    ok: bool
    errors: List[str] = []
    warnings: List[str] = []
    bad_nodes: List[str] = []        # canvas tô đỏ đúng node này


class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    graph: WorkflowGraphIn
    enabled: bool = True


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    graph: Optional[WorkflowGraphIn] = None
    enabled: Optional[bool] = None


class WorkflowOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    graph: dict
    enabled: bool
    created_at: datetime
    updated_at: Optional[datetime]


class WorkflowSummary(BaseModel):
    id: int
    name: str
    description: Optional[str]
    enabled: bool
    node_count: int
    claude_nodes: List[str] = []     # node dùng Claude (đều đã có gate chắn trước)
    created_at: datetime


class WorkflowRunStart(BaseModel):
    trigger_type: str = "manual_trigger"
    payload: dict = {}


class WorkflowRunOut(BaseModel):
    id: int
    workflow_id: int
    trigger_type: str
    status: str
    payload: dict = {}
    state: dict = {}
    outputs: dict = {}
    waiting_on: List[str] = []
    approvals: List[dict] = []
    log: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class WorkflowClaimOut(BaseModel):
    """Executor trên host nhận đủ thứ cần để chạy tiếp, không phải query thêm."""
    run_id: int
    workflow_id: int
    workflow_name: str
    trigger_type: str
    graph: dict
    state: dict = {}
    payload: dict = {}
    # gate node_id → epoch seconds; executor dùng để kiểm tra cú bấm còn tươi
    approvals: dict = {}
    started_at: Optional[datetime] = None


class WorkflowRunComplete(BaseModel):
    status: str                      # waiting / done / failed
    state: dict = {}
    outputs: dict = {}
    log: Optional[str] = None
    error: Optional[str] = None


class WorkflowApprove(BaseModel):
    node_id: str
    approved_by: Optional[str] = None
    note: Optional[str] = None


class SettingOut(BaseModel):
    key: str
    value: str

    model_config = {"from_attributes": True}


class SettingUpdate(BaseModel):
    value: str


# ── Project ──

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    status: str = "active"
    client_folder: Optional[str] = None
    git_url: Optional[str] = None
    doc_url: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    client_folder: Optional[str] = None
    git_url: Optional[str] = None
    doc_url: Optional[str] = None
    agent_ids: Optional[List[int]] = None


class ProjectOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: str
    client_folder: Optional[str]
    git_url: Optional[str]
    doc_url: Optional[str]
    created_at: datetime
    agents: List["AgentOut"] = []

    model_config = {"from_attributes": True}


class ProjectSummary(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: str
    client_folder: Optional[str]
    git_url: Optional[str]
    doc_url: Optional[str]
    created_at: datetime
    agent_count: int

    model_config = {"from_attributes": True}


# ── Agent ──

class AgentCreate(BaseModel):
    name: str
    role: str
    model: str = "gpt-4o"
    status: str = "available"
    description: Optional[str] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None


class AgentOut(BaseModel):
    id: int
    name: str
    role: str
    model: str
    status: str
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentDetailOut(AgentOut):
    projects: List["ProjectSummary"] = []

    model_config = {"from_attributes": True}


# ── Project Task ──

class TaskDocCreate(BaseModel):
    title: str
    content: str = ""
    doc_type: str = "note"


class TaskDocOut(BaseModel):
    id: int
    task_id: int
    title: str
    content: str
    doc_type: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectTaskCreate(BaseModel):
    name: str
    description: Optional[str] = None
    priority: str = "medium"
    assigned_agent_id: Optional[int] = None
    due_at: Optional[datetime] = None


class ProjectTaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    progress: Optional[int] = None
    assigned_agent_id: Optional[int] = None
    due_at: Optional[datetime] = None


class ProjectTaskOut(BaseModel):
    id: int
    project_id: int
    assigned_agent_id: Optional[int]
    name: str
    description: Optional[str]
    status: str
    priority: str
    progress: int
    due_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    agent: Optional["AgentOut"] = None
    documents: List["TaskDocOut"] = []
    comments: List["TaskCommentOut"] = []
    subtasks: List["SubTaskOut"] = []

    model_config = {"from_attributes": True}


# ── Task Comment ──

class TaskCommentCreate(BaseModel):
    author: str
    content: str


class TaskCommentOut(BaseModel):
    id: int
    task_id: int
    author: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── SubTask ──

class SubTaskCreate(BaseModel):
    name: str
    assigned_agent_id: Optional[int] = None


class SubTaskUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    assigned_agent_id: Optional[int] = None


class SubTaskOut(BaseModel):
    id: int
    task_id: int
    name: str
    status: str
    assigned_agent_id: Optional[int]
    created_at: datetime
    agent: Optional["AgentOut"] = None

    model_config = {"from_attributes": True}
