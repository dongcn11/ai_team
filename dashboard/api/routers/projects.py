from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List
import os
from pathlib import Path

from database import get_db
from models import Project, Agent, ProjectTask, TaskComment, SubTask
from schemas import ProjectCreate, ProjectUpdate, ProjectOut, ProjectSummary
from system_config import get_system_agents

CLIENTS_DIR = Path(os.getenv("CLIENTS_DIR", "/clients"))
CONFIG_FILE = Path(os.getenv("CONFIG_DIR", "../config")) / "settings.toml"


def _create_client_folder(folder_name: str):
    """Tạo folder clients/<folder_name>/settings.toml từ config gốc của hệ thống."""
    folder_path = CLIENTS_DIR / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    # Read the actual system config as base template
    if CONFIG_FILE.exists():
        content = CONFIG_FILE.read_text(encoding="utf-8")
    else:
        content = '[agents]\n[slack]\n[output]\n[timeouts]\n[tech_stack]\n'

    # Update output directory to be per-project
    lines = []
    for line in content.splitlines():
        if line.strip().startswith("directory"):
            lines.append(f'directory = "./output/{folder_name}"')
        else:
            lines.append(line)

    settings_file = folder_path / "settings.toml"
    settings_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[Projects] Created client folder: {folder_path}")

router = APIRouter()


@router.get("/", response_model=List[ProjectSummary])
def list_projects(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Project).order_by(desc(Project.created_at))
    if status:
        q = q.filter(Project.status == status)
    projects = q.all()
    return [
        ProjectSummary(
            id=proj.id,
            name=proj.name,
            description=proj.description,
            status=proj.status,
            git_url=proj.git_url,
            doc_url=proj.doc_url,
            client_folder=proj.client_folder,
            created_at=proj.created_at,
            agent_count=len(proj.agents),
        )
        for proj in projects
    ]


@router.post("/", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    folder_name = payload.client_folder or payload.name.lower().replace(" ", "_")[:30]
    proj = Project(
        name=payload.name,
        description=payload.description,
        status=payload.status,
        client_folder=folder_name,
        git_url=payload.git_url,
        doc_url=payload.doc_url,
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)

    # Create client folder on filesystem
    try:
        _create_client_folder(folder_name)
    except Exception as e:
        print(f"[Projects] Warning: Could not create client folder: {e}")

    # Auto-sync agents from system config (ưu tiên project settings)
    try:
        settings_path = CLIENTS_DIR / folder_name / "settings.toml"
        system_agents = get_system_agents(settings_path if settings_path.exists() else None)
        for sa in system_agents:
            existing = db.query(Agent).filter(Agent.role == sa["key"]).first()
            if not existing:
                agent = Agent(
                    name=sa["name"],
                    role=sa["key"],
                    model=sa["model"],
                    description=sa["description"],
                )
                db.add(agent)
                db.flush()
                existing = agent
            else:
                existing.model = sa["model"]
                existing.name = sa["name"]
                existing.description = sa["description"]
            if existing not in proj.agents:
                proj.agents.append(existing)
        db.commit()
        db.refresh(proj)
        print(f"[Projects] Synced {len(system_agents)} agents from system config")
    except Exception as e:
        print(f"[Projects] Warning: Could not sync agents: {e}")

    return proj


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    if payload.name is not None:
        proj.name = payload.name
    if payload.description is not None:
        proj.description = payload.description
    if payload.status is not None:
        proj.status = payload.status
    if payload.client_folder is not None:
        proj.client_folder = payload.client_folder
    if payload.git_url is not None:
        proj.git_url = payload.git_url
    if payload.doc_url is not None:
        proj.doc_url = payload.doc_url
    if payload.agent_ids is not None:
        agents = db.query(Agent).filter(Agent.id.in_(payload.agent_ids)).all()
        proj.agents = agents

    db.commit()
    db.refresh(proj)
    return proj


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(proj)
    db.commit()
    return {"ok": True}


@router.post("/{project_id}/agents/{agent_id}")
def assign_agent(project_id: int, agent_id: int, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent not in proj.agents:
        proj.agents.append(agent)
        db.commit()
    return {"ok": True}


@router.delete("/{project_id}/agents/{agent_id}")
def remove_agent(project_id: int, agent_id: int, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent in proj.agents:
        proj.agents.remove(agent)
        db.commit()
    return {"ok": True}


@router.post("/{project_id}/sync-agents")
def sync_agents(project_id: int, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        # Ưu tiên đọc từ project-specific settings.toml
        settings_path = CLIENTS_DIR / (proj.client_folder or "") / "settings.toml"
        system_agents = get_system_agents(settings_path if settings_path.exists() else None)
        for sa in system_agents:
            existing = db.query(Agent).filter(Agent.role == sa["key"]).first()
            if not existing:
                agent = Agent(
                    name=sa["name"],
                    role=sa["key"],
                    model=sa["model"],
                    description=sa["description"],
                )
                db.add(agent)
                db.flush()
                existing = agent
            else:
                existing.model = sa["model"]
                existing.name = sa["name"]
                existing.description = sa["description"]
            if existing not in proj.agents:
                proj.agents.append(existing)
        db.commit()
        db.refresh(proj)
        return {"ok": True, "count": len(system_agents)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/activity")
def project_activity(project_id: int, limit: int = 50, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    entries = []

    tasks = db.query(ProjectTask).filter(ProjectTask.project_id == project_id).all()
    for t in tasks:
        entries.append({
            "time": t.created_at.isoformat(),
            "type": "task_created",
            "text": f"Task '{t.name}' created",
            "agent": t.agent.name if t.agent else None,
            "priority": t.priority,
        })
        if t.status != "todo":
            entries.append({
                "time": t.updated_at.isoformat(),
                "type": f"task_{t.status}",
                "text": f"Task '{t.name}' → {t.status.replace('_', ' ')} (progress: {t.progress}%)",
                "agent": t.agent.name if t.agent else None,
                "priority": t.priority,
            })
        if t.completed_at:
            entries.append({
                "time": t.completed_at.isoformat(),
                "type": "task_done",
                "text": f"Task '{t.name}' completed",
                "agent": t.agent.name if t.agent else None,
                "priority": t.priority,
            })

    comments = (
        db.query(TaskComment)
        .join(ProjectTask)
        .filter(ProjectTask.project_id == project_id)
        .order_by(TaskComment.created_at)
        .all()
    )
    for c in comments:
        entries.append({
            "time": c.created_at.isoformat(),
            "type": "comment",
            "text": f"{c.author}: {c.content[:100]}{'...' if len(c.content) > 100 else ''}",
            "agent": c.author,
        })

    subtasks = (
        db.query(SubTask)
        .join(ProjectTask)
        .filter(ProjectTask.project_id == project_id)
        .order_by(SubTask.created_at)
        .all()
    )
    for s in subtasks:
        prefix = "✓" if s.status == "done" else "○"
        agent_name = s.agent.name if s.agent else "unassigned"
        entries.append({
            "time": s.created_at.isoformat(),
            "type": "subtask",
            "text": f"{prefix} SubTask: {s.name} ({agent_name})",
            "agent": agent_name,
        })

    entries.sort(key=lambda e: e["time"], reverse=True)
    return entries[:limit]
