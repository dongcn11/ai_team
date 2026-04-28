from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List

from database import get_db
from models import Run, Task
from schemas import RunCreate, RunOut, RunSummary

router = APIRouter()


@router.post("/", response_model=RunOut)
def create_run(run: RunCreate, db: Session = Depends(get_db)):
    db_run = Run(
        client=run.client,
        profile=run.profile,
        project_id=run.project_id,
        status="running",
    )
    db.add(db_run)
    db.flush()

    for t in run.tasks:
        db.add(Task(run_id=db_run.id, role=t.role, description=t.description))

    db.commit()
    db.refresh(db_run)
    return db_run


@router.get("/current", response_model=RunOut)
def get_current_run(db: Session = Depends(get_db)):
    run = (
        db.query(Run)
        .filter(Run.status == "running")
        .order_by(desc(Run.id))
        .first()
    )
    if not run:
        run = db.query(Run).order_by(desc(Run.id)).first()
    if not run:
        raise HTTPException(status_code=404, detail="No runs found")
    return run


@router.get("/", response_model=List[RunSummary])
def list_runs(skip: int = 0, limit: int = 20, project_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Run).order_by(desc(Run.id))
    if project_id:
        q = q.filter(Run.project_id == project_id)
    runs = q.offset(skip).limit(limit).all()
    result = []
    for run in runs:
        total  = len(run.tasks)
        done   = sum(1 for t in run.tasks if t.status == "done")
        failed = sum(1 for t in run.tasks if t.status == "failed")
        result.append(
            RunSummary(
                id=run.id,
                project_id=run.project_id,
                client=run.client,
                profile=run.profile,
                started_at=run.started_at,
                finished_at=run.finished_at,
                status=run.status,
                total_tasks=total,
                done_tasks=done,
                failed_tasks=failed,
            )
        )
    return result


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
