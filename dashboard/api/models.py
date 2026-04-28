from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Table, Float
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
    due_at           = Column(DateTime, nullable=True)
    completed_at     = Column(DateTime, nullable=True)
    created_at       = Column(DateTime, server_default=func.now())
    updated_at       = Column(DateTime, server_default=func.now(), onupdate=func.now())

    project  = relationship("Project", back_populates="tasks")
    agent    = relationship("Agent", back_populates="tasks")
    documents = relationship("TaskDocument", back_populates="task", cascade="all, delete-orphan")
    comments  = relationship("TaskComment", back_populates="task", cascade="all, delete-orphan")
    subtasks  = relationship("SubTask",    back_populates="task", cascade="all, delete-orphan")


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
