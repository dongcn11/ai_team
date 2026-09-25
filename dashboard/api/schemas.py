from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
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


class WorkflowStepJobOut(BaseModel):
    id: int
    run_id: int
    node_id: str
    node_label: Optional[str]
    client_folder: Optional[str]
    file_path: Optional[str]
    prompt: str
    tool: str = "claude"
    model: Optional[str] = None
    # Thư mục code của project — worker truyền cho CLI qua --add-dir
    add_dirs: List[str] = []
    agent_key: Optional[str] = None
    # Tài khoản Claude người dùng chọn ở Settings + có cho worker tự chuyển khi hết
    # quota không. Đọc lúc claim (không phải lúc tạo job) để đổi lựa chọn là bước
    # KẾ TIẾP ăn ngay. Chỉ là TÊN — token nằm trên host, worker tự tra.
    claude_account: Optional[str] = None
    claude_auto_switch: bool = True
    status: str
    output: Optional[str]
    error: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    # Số liệu đo được của lần chạy: model thật sự chạy, token, tiền, thời gian
    model_used: Optional[str] = None
    cost_usd: Optional[float] = None
    usage: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None

    model_config = {"from_attributes": True}


class ClaudeAccountState(BaseModel):
    """Trạng thái 1 tài khoản Claude worker đang cầm — không có token."""
    name: str = Field(max_length=100)
    state: Literal["ready", "cooling", "error"]
    until: Optional[str] = None    # ISO UTC, chỉ khi cooling
    note: Optional[str] = Field(default=None, max_length=300)


class McpRuntimeState(BaseModel):
    """Kết quả nối MCP của lần chạy gần nhất. Không có trường bí mật."""
    slug:   str
    server: str
    status: str
    at:     Optional[str] = None


class WorkflowStepJobClaim(BaseModel):
    """Body worker gửi khi hỏi việc. Worker cũ gửi `{}` → accounts None → giữ snapshot cũ."""
    accounts: Optional[List[ClaudeAccountState]] = Field(default=None, max_length=50)
    mcp: Optional[List[McpRuntimeState]] = Field(default=None, max_length=200)


class AgentQuestionOut(BaseModel):
    id: int
    run_id: int
    workflow_id: Optional[int] = None
    node_id: str
    node_label: Optional[str] = None
    client_folder: Optional[str] = None
    task_file: Optional[str] = None
    question: str
    status: str
    answer: Optional[str] = None
    created_at: datetime
    answered_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AgentQuestionAnswer(BaseModel):
    answer: str


class WorkflowStepJobComplete(BaseModel):
    status: str            # done | failed
    output: Optional[str] = None
    error: Optional[str] = None
    # Số liệu worker đo được từ sự kiện `result` của CLI
    model_used: Optional[str] = None
    cost_usd: Optional[float] = None
    usage: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None


class WorkflowStepJobProgress(BaseModel):
    """1 đợt log worker đẩy lên trong lúc bước đang chạy — nối vào đuôi job.progress."""
    lines: str


class WorkflowStepJobProgressOut(BaseModel):
    """Log sống của 1 job. Tách khỏi WorkflowStepJobOut để list job (poll 4s) không
    phải kéo theo 16KB log của mỗi job."""
    id: int
    status: str
    progress: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


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
    agent_key: Optional[str] = None
    due_at: Optional[datetime] = None


class ProjectTaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    progress: Optional[int] = None
    assigned_agent_id: Optional[int] = None
    agent_key: Optional[str] = None
    due_at: Optional[datetime] = None


class ProjectTaskOut(BaseModel):
    id: int
    project_id: int
    assigned_agent_id: Optional[int]
    agent_key: Optional[str] = None
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


# ── Workflow ──

class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    client_folder: Optional[str] = None
    definition: Dict[str, Any] = {"nodes": [], "edges": []}


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    client_folder: Optional[str] = None
    auto_run: Optional[bool] = None
    definition: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class WorkflowOut(BaseModel):
    id: int
    project_id: Optional[int]
    client_folder: Optional[str] = None
    name: str
    description: Optional[str]
    definition: Dict[str, Any]
    is_active: bool
    auto_run: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowRunOut(BaseModel):
    id: int
    workflow_id: int
    task_id: Optional[int] = None
    status: str
    node_status: Dict[str, str]
    log: List[Dict[str, Any]]
    created_at: datetime
    finished_at: Optional[datetime]

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


# ── Bot chat (Telegram/Slack) ────────────────────────────────────────────────

class ChatBotBase(BaseModel):
    platform: str                      # telegram | slack
    name: str
    chats: str = ""                    # chat id / #kênh, cách nhau dấu phẩy
    client_folder: Optional[str] = None   # None = mọi dự án
    workflow_ids: List[int] = []          # [] = mọi workflow của dự án đó
    enabled: bool = True


class ChatBotCreate(ChatBotBase):
    token: str = ""
    signing_secret: Optional[str] = None
    app_token: Optional[str] = None


class ChatBotUpdate(BaseModel):
    """Trường nào None = không đụng tới. Token/secret gửi chuỗi rỗng cũng coi như
    không đổi — để sửa tên bot mà không phải dán lại token."""
    name: Optional[str] = None
    chats: Optional[str] = None
    client_folder: Optional[str] = None
    workflow_ids: Optional[List[int]] = None
    enabled: Optional[bool] = None
    token: Optional[str] = None
    signing_secret: Optional[str] = None
    app_token: Optional[str] = None
    clear_client_folder: bool = False   # đặt lại về "mọi dự án"


class ChatBotOut(BaseModel):
    id: int
    platform: str
    name: str
    chats: str
    client_folder: Optional[str]
    workflow_ids: List[int] = []
    enabled: bool
    created_at: Optional[datetime] = None
    # Token KHÔNG bao giờ trả ra ngoài — chỉ đủ để nhận ra là cái nào
    token_hint: str = ""
    has_token: bool = False
    has_secret: bool = False
    has_app_token: bool = False
    # "socket" = WebSocket đi ra (không cần URL công khai) · "webhook" = Slack gọi vào
    mode: Optional[str] = None
    # Suy ra ở server để UI khỏi phải tự ghép
    scope_label: str = ""
    request_path: Optional[str] = None   # chỉ Slack
    running: bool = False
    me: Optional[str] = None
    last_error: Optional[str] = None
    # workflow_ids trỏ tới workflow đã bị xoá — hiện cảnh báo thay vì dọn ngầm
    stale_workflow_ids: List[int] = []

    model_config = {"from_attributes": True}


# ── Skill (kho file trong skills/, xem skills_store.py) ───────────────────

class SkillResource(BaseModel):
    """1 file phụ trong skill thư mục — script, mẫu, dữ liệu, thư mục con."""
    path: str                   # tương đối so với thư mục skill
    size: int = 0
    is_text: bool = True        # false = nhị phân, chỉ tải về được
    kind: str = "data"          # doc | script | data | binary


class SkillOut(BaseModel):
    """1 skill = 1 SKILL.md (hoặc 1 file .md kiểu cũ) trong skills/<category>/."""
    id: str                     # "<category>/<slug>"
    category: str
    slug: str
    name: str
    description: str = ""
    tags: List[str] = []
    format: str = "folder"      # folder (SKILL.md + file phụ) | file (.md đơn lẻ)
    path: str = ""              # đường dẫn tương đối repo, để mở bằng editor
    chars: int = 0
    updated_at: Optional[str] = None
    has_frontmatter: bool = False
    resources: List[SkillResource] = []   # script, mẫu, thư mục con…


class SkillDetailOut(SkillOut):
    body: str = ""              # phần thân, đã bỏ frontmatter
    content: str = ""           # nguyên văn file


class SkillCreate(BaseModel):
    category: str
    name: str
    description: str = ""
    body: str = ""
    slug: Optional[str] = None          # bỏ trống = slugify(name)
    tags: List[str] = []
    format: str = "folder"


class SkillUpdate(BaseModel):
    """None = không đụng tới. Đổi category/slug là DI CHUYỂN file → id đổi theo."""
    name: Optional[str] = None
    description: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None
    slug: Optional[str] = None


class SkillDuplicate(BaseModel):
    slug: Optional[str] = None
    category: Optional[str] = None


class SkillResourceWrite(BaseModel):
    content: str = ""



# ── MCP theo từng dự án ──────────────────────────────────────────────────────
# Không schema nào ở đây có trường chứa giá trị credential. Cố ý.

class McpProfileOut(BaseModel):
    name: str
    tools: List[str] = []


class McpTemplateOut(BaseModel):
    name: str
    version: str = ""
    needs_credential: bool = False
    profiles: List[McpProfileOut] = []


class McpServerIn(BaseModel):
    name: str
    template: str
    profile: str = "read-only"
    enabled: bool = True
    declared_write_scope: dict = {}


class McpServerOut(McpServerIn):
    # Credential đã được KHAI trong settings.local.toml hay chưa. Không phải
    # "dùng được" — API chạy trong container, không thấy đường dẫn trên host.
    # Worker mới biết file có thật không, và nó báo qua heartbeat.
    credential_declared: bool = False


class McpConfigIn(BaseModel):
    enabled: bool = True
    servers: List[McpServerIn] = []


class McpConfigOut(BaseModel):
    slug: str
    enabled: bool = True
    servers: List[McpServerOut] = []
    exists: bool = False
    writable: bool = False
    parse_error: Optional[str] = None


# --- Lịch chạy định kỳ theo dự án (xem models.Schedule, scheduler.py) --------

class ScheduleIn(BaseModel):
    name: str
    cron_expression: str                     # unix-cron 5 trường
    timezone: str = "Asia/Ho_Chi_Minh"       # tên tz database
    enabled: bool = True
    job_kind: Literal["scan_docs"] = "scan_docs"
    misfire_policy: Literal["catchup_once", "skip"] = "catchup_once"
    concurrency_policy: Literal["forbid", "allow"] = "forbid"
    on_change: Literal["notify", "run_workflow", "both"] = "notify"
    workflow_id: Optional[int] = None        # bắt buộc khi on_change != notify
    jitter_s: int = Field(default=0, ge=0, le=3600)


class ScheduleOut(ScheduleIn):
    id: int
    project_id: int
    next_run_at: Optional[datetime] = None   # UTC
    last_run_at: Optional[datetime] = None   # UTC
    last_status: Optional[str] = None
    last_detail: Optional[str] = None

    class Config:
        from_attributes = True


class SchedulePreviewOut(BaseModel):
    """N mốc chạy kế tiếp theo GIỜ ĐỊA PHƯƠNG của lịch — để người dùng tự kiểm
    chứng biểu thức cron trước khi lưu, thay vì đợi tới 6h sáng mới biết sai."""
    cron_expression: str
    timezone: str
    next_runs: List[str] = []                # ISO-8601 có offset
