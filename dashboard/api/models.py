from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Table, Float, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


project_agents = Table(
    "project_agents",
    Base.metadata,
    Column("project_id", Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("agent_id",   Integer, ForeignKey("agents.id",   ondelete="CASCADE"), primary_key=True),
)


class Run(Base):
    __tablename__ = "runs"

    id          = Column(Integer, primary_key=True, index=True)
    project_id  = Column(Integer, ForeignKey("projects.id"), nullable=True)
    client      = Column(String, nullable=True)
    profile     = Column(String, nullable=True)
    started_at  = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)
    status      = Column(String, default="running")  # running / done / failed

    tasks  = relationship("Task",  back_populates="run", cascade="all, delete-orphan")
    issues = relationship("Issue", back_populates="run", cascade="all, delete-orphan")


class RunJob(Base):
    """Hàng đợi trigger pipeline từ Dashboard. worker.py (host) poll bảng này,
    chạy tuần tự từng job qua `python main.py`. KHÔNG trùng với `runs` —
    `runs` là bản ghi thực thi do orchestrator tự tạo khi nó khởi động."""
    __tablename__ = "run_jobs"

    id            = Column(Integer, primary_key=True, index=True)
    client_folder = Column(String, nullable=False)   # slug → clients/{slug}
    project_id    = Column(Integer, nullable=True)    # Project.id (để wire FEATURE_IDS)
    profile       = Column(String, nullable=True)     # override profile (optional)
    feature_ids   = Column(Text, nullable=True)       # csv ProjectTask.id sẽ mark done
    status        = Column(String, default="queued")  # queued/running/done/failed/canceled
    run_id        = Column(Integer, nullable=True)    # link sang runs.id (best-effort)
    error         = Column(Text, nullable=True)
    created_at    = Column(DateTime, server_default=func.now())
    started_at    = Column(DateTime, nullable=True)
    finished_at   = Column(DateTime, nullable=True)


class Task(Base):
    __tablename__ = "tasks"

    id          = Column(Integer, primary_key=True, index=True)
    run_id      = Column(Integer, ForeignKey("runs.id"), nullable=False)
    role        = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status      = Column(String, default="pending")  # pending/running/done/failed
    started_at  = Column(String, nullable=True)   # "HH:MM:SS" string
    finished_at = Column(String, nullable=True)
    duration_s  = Column(Integer, nullable=True)
    error       = Column(Text, nullable=True)

    run = relationship("Run", back_populates="tasks")


class Issue(Base):
    __tablename__ = "issues"

    id          = Column(Integer, primary_key=True, index=True)
    run_id      = Column(Integer, ForeignKey("runs.id"), nullable=False)
    role        = Column(String, nullable=False)
    severity    = Column(String, default="medium")  # high / medium / low
    description = Column(Text, nullable=True)
    suggestion  = Column(Text, nullable=True)
    created_at  = Column(DateTime, server_default=func.now())

    run = relationship("Run", back_populates="issues")


class Setting(Base):
    __tablename__ = "settings"

    key   = Column(String, primary_key=True)
    value = Column(String, nullable=False, default="")


class Project(Base):
    __tablename__ = "projects"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status       = Column(String, default="active")  # active / paused / completed / archived
    client_folder = Column(String, nullable=True)
    git_url      = Column(String, nullable=True)
    doc_url     = Column(String, nullable=True)
    created_at  = Column(DateTime, server_default=func.now())

    agents = relationship("Agent", secondary=project_agents, back_populates="projects")
    tasks  = relationship("ProjectTask", back_populates="project", cascade="all, delete-orphan")


class Agent(Base):
    __tablename__ = "agents"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, nullable=False)
    role        = Column(String, nullable=False)
    model       = Column(String, default="gpt-4o")
    status      = Column(String, default="available")  # available / busy / offline
    description = Column(Text, nullable=True)
    created_at  = Column(DateTime, server_default=func.now())

    projects = relationship("Project", secondary=project_agents, back_populates="agents")
    tasks    = relationship("ProjectTask", back_populates="agent")


class ProjectTask(Base):
    __tablename__ = "project_tasks"

    id               = Column(Integer, primary_key=True, index=True)
    project_id       = Column(Integer, ForeignKey("projects.id"), nullable=False)
    assigned_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    # Workflow mà task này chạy theo. Mỗi project có danh sách workflow riêng,
    # mỗi task chọn 1 workflow trong danh sách đó (NULL = chưa chọn).
    workflow_id      = Column(Integer, ForeignKey("workflows.id"), nullable=True)
    name             = Column(String, nullable=False)
    description      = Column(Text, nullable=True)
    status           = Column(String, default="todo")     # todo / in_progress / review / done
    priority         = Column(String, default="medium")   # high / medium / low
    progress         = Column(Integer, default=0)         # 0-100
    acceptance_criteria = Column(Text, nullable=True)     # acceptance criteria / notes (multi-line)
    due_at           = Column(DateTime, nullable=True)
    completed_at     = Column(DateTime, nullable=True)
    created_at       = Column(DateTime, server_default=func.now())
    updated_at       = Column(DateTime, server_default=func.now(), onupdate=func.now())

    project  = relationship("Project", back_populates="tasks")
    agent    = relationship("Agent", back_populates="tasks")
    workflow = relationship("Workflow", back_populates="tasks")
    workflow_runs = relationship("WorkflowRun", back_populates="task", cascade="all, delete-orphan")
    documents = relationship("TaskDocument", back_populates="task", cascade="all, delete-orphan")
    comments  = relationship("TaskComment", back_populates="task", cascade="all, delete-orphan")
    subtasks  = relationship("SubTask",    back_populates="task", cascade="all, delete-orphan")
    files     = relationship("FeatureFile", back_populates="task", cascade="all, delete-orphan")


class FeatureFile(Base):
    __tablename__ = "feature_files"

    id                = Column(Integer, primary_key=True, index=True)
    task_id           = Column(Integer, ForeignKey("project_tasks.id"), nullable=False)
    filename          = Column(String, nullable=False)   # stored name on disk
    original_filename = Column(String, nullable=False)   # name as uploaded
    description       = Column(Text, nullable=True)
    size              = Column(Integer, default=0)
    content_type      = Column(String, nullable=True)
    uploaded_at       = Column(DateTime, server_default=func.now())

    task = relationship("ProjectTask", back_populates="files")


class TaskDocument(Base):
    __tablename__ = "task_documents"

    id         = Column(Integer, primary_key=True, index=True)
    task_id    = Column(Integer, ForeignKey("project_tasks.id"), nullable=False)
    title      = Column(String, nullable=False)
    content    = Column(Text, nullable=True, default="")
    doc_type   = Column(String, default="note")  # note / spec / log / result
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    task = relationship("ProjectTask", back_populates="documents")


class TaskComment(Base):
    __tablename__ = "task_comments"

    id         = Column(Integer, primary_key=True, index=True)
    task_id    = Column(Integer, ForeignKey("project_tasks.id"), nullable=False)
    author     = Column(String, nullable=False)
    content    = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    task = relationship("ProjectTask", back_populates="comments")


class Workflow(Base):
    """Định nghĩa workflow kéo-thả: chuỗi trigger + action node do user tự thiết kế.
    `definition` lưu {"nodes": [...], "edges": [...]} dạng React Flow — không tách
    bảng riêng cho từng loại node để giữ linh hoạt khi thêm node type mới."""
    __tablename__ = "workflows"

    id          = Column(Integer, primary_key=True, index=True)
    project_id  = Column(Integer, ForeignKey("projects.id"), nullable=True)
    name        = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    definition  = Column(JSON, nullable=False, default=lambda: {"nodes": [], "edges": []})
    is_active   = Column(Boolean, default=True)
    # BẬT = mỗi bước được host worker tự chạy bằng `claude -p` (headless) thay vì
    # chờ người dùng dán lệnh vào terminal. Mặc định TẮT — xem docstring
    # WorkflowStepJob về giới hạn cố ý của chế độ này.
    auto_run    = Column(Boolean, default=False)
    created_at  = Column(DateTime, server_default=func.now())
    updated_at  = Column(DateTime, server_default=func.now(), onupdate=func.now())

    runs = relationship("WorkflowRun", back_populates="workflow", cascade="all, delete-orphan")
    project = relationship("Project")
    tasks = relationship("ProjectTask", back_populates="workflow")

    @property
    def client_folder(self):
        return self.project.client_folder if self.project else None


class WorkflowStepJob(Base):
    """Hàng đợi 1 bước workflow cho worker trên host chạy bằng Claude headless.

    Tại sao phải qua hàng đợi: API chạy trong container — không có CLI `claude`,
    không có thư mục repo thật, không có phiên đăng nhập của bạn. worker.py chạy
    TRÊN MÁY BẠN mới chạy được, nên API chỉ ghi job, worker poll và thực thi.

    Giới hạn cố ý (khác hẳn pipeline `ai_team/` — nơi Claude Code bị chặn cứng):
    chỉ chạy trên máy của chính bạn, bằng đăng nhập của bạn, TUẦN TỰ 1 bước/lần,
    và phải bật thủ công cho từng workflow (`workflows.auto_run`)."""
    __tablename__ = "workflow_step_jobs"

    id            = Column(Integer, primary_key=True, index=True)
    run_id        = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    node_id       = Column(String, nullable=False)
    node_label    = Column(String, nullable=True)
    client_folder = Column(String, nullable=True)    # slug project → cwd cho CLI
    file_path     = Column(Text, nullable=True)      # đường dẫn file task (tương đối repo)
    prompt        = Column(Text, nullable=False)     # prompt truyền cho CLI
    # Công cụ chạy bước này: "claude" (headless, mặc định) hoặc "opencode" khi node
    # chọn 1 agent của pipeline. Model đi kèm agent đó.
    tool          = Column(String, default="claude")
    model         = Column(String, nullable=True)
    status        = Column(String, default="queued") # queued/running/done/failed/canceled
    output        = Column(Text, nullable=True)      # stdout cắt ngắn, để soi khi lỗi
    error         = Column(Text, nullable=True)
    created_at    = Column(DateTime, server_default=func.now())
    started_at    = Column(DateTime, nullable=True)
    finished_at   = Column(DateTime, nullable=True)


class WorkflowRun(Base):
    """Log 1 lần 'Test run' của workflow. Phase 1: chỉ mô phỏng (không gọi
    Slack/Git/opencode thật) — dùng để render trạng thái từng node lên canvas."""
    __tablename__ = "workflow_runs"

    id          = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    # Task đã kích hoạt lần chạy này (NULL = chạy thủ công từ trình soạn workflow
    # hoặc từ trigger Slack, không gắn task nào).
    task_id     = Column(Integer, ForeignKey("project_tasks.id"), nullable=True)
    status      = Column(String, default="running")  # running / done / failed / cancelled
    node_status = Column(JSON, default=dict)          # {node_id: "pending"|"running"|"ok"|"error"}
    log         = Column(JSON, default=list)           # [{node_id, message, ts}]
    created_at  = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)

    workflow = relationship("Workflow", back_populates="runs")
    task     = relationship("ProjectTask", back_populates="workflow_runs")


class SubTask(Base):
    __tablename__ = "subtasks"

    id               = Column(Integer, primary_key=True, index=True)
    task_id          = Column(Integer, ForeignKey("project_tasks.id"), nullable=False)
    name             = Column(String, nullable=False)
    status           = Column(String, default="todo")  # todo / done
    assigned_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    created_at       = Column(DateTime, server_default=func.now())

    task  = relationship("ProjectTask", back_populates="subtasks")
    agent = relationship("Agent")
