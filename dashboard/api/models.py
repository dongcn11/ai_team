from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Run(Base):
    __tablename__ = "runs"

    id          = Column(Integer, primary_key=True, index=True)
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
