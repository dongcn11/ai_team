from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Text, Table, Float
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


class Workflow(Base):
    """Workflow do user tự vẽ. `graph_json` là định nghĩa node/edge — chỉ được
    lưu khi `ai_team.workflow.graph.validate()` pass, nên mọi row trong bảng này
    đã đảm bảo không có node Claude nào bị auto-trigger kích trực tiếp."""
    __tablename__ = "workflows"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    graph_json  = Column(Text, nullable=False)
    enabled     = Column(Boolean, default=True)
    created_at  = Column(DateTime, server_default=func.now())
    updated_at  = Column(DateTime, server_default=func.now(), onupdate=func.now())

    runs = relationship("WorkflowRun", back_populates="workflow",
                        cascade="all, delete-orphan")


class WorkflowRun(Base):
    """Một lần chạy. `state_json` = {node_id: status} do executor cập nhật.
    Executor trên host claim run này (tuần tự, 1 run/lần), chạy tới khi gặp gate
    chưa duyệt rồi trả state về — không giữ process chờ."""
    __tablename__ = "workflow_runs"

    id           = Column(Integer, primary_key=True, index=True)
    workflow_id  = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    trigger_type = Column(String, nullable=False, default="manual_trigger")
    status       = Column(String, default="queued")   # queued/running/waiting/done/failed/canceled
    payload_json = Column(Text, nullable=True)        # dữ liệu trigger đưa vào
    state_json   = Column(Text, nullable=True)        # {node_id: status}
    outputs_json = Column(Text, nullable=True)        # {node_id: output}
    log          = Column(Text, nullable=True)
    error        = Column(Text, nullable=True)
    created_at   = Column(DateTime, server_default=func.now())
    started_at   = Column(DateTime, nullable=True)
    finished_at  = Column(DateTime, nullable=True)

    workflow  = relationship("Workflow", back_populates="runs")
    approvals = relationship("WorkflowApproval", back_populates="run",
                             cascade="all, delete-orphan")


class WorkflowApproval(Base):
    """Bằng chứng có người bấm duyệt tại một `manual_gate`.

    Đây là artifact quan trọng nhất của cả hệ: node `runtime="claude"` chỉ được
    chạy khi tồn tại approval upstream và `approved_at` còn tươi. Xoá/sửa bảng
    này = node Claude bị chặn, không phải được thả."""
    __tablename__ = "workflow_approvals"

    id          = Column(Integer, primary_key=True, index=True)
    run_id      = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    node_id     = Column(String, nullable=False)
    approved_by = Column(String, nullable=True)
    note        = Column(Text, nullable=True)
    approved_at = Column(DateTime, server_default=func.now())

    run = relationship("WorkflowRun", back_populates="approvals")


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
