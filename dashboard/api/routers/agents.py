from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List

from database import get_db
from models import Agent
from schemas import AgentCreate, AgentUpdate, AgentOut, AgentDetailOut, ProjectSummary

router = APIRouter()


@router.get("/", response_model=List[AgentOut])
def list_agents(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Agent).order_by(desc(Agent.created_at))
    if status:
        q = q.filter(Agent.status == status)
    return q.all()


@router.post("/", response_model=AgentOut)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    agent = Agent(
        name=payload.name,
        role=payload.role,
        model=payload.model,
        status=payload.status,
        description=payload.description,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentDetailOut)
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: int, payload: AgentUpdate, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if payload.name is not None:
        agent.name = payload.name
    if payload.role is not None:
        agent.role = payload.role
    if payload.model is not None:
        agent.model = payload.model
    if payload.status is not None:
        agent.status = payload.status
    if payload.description is not None:
        agent.description = payload.description

    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}")
def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"ok": True}
