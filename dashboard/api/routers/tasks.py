from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from models import Run, Task
from schemas import TaskUpdate, TaskOut

router = APIRouter()


@router.post("/update", response_model=TaskOut)
def update_task(payload: TaskUpdate, db: Session = Depends(get_db)):
    task = (
        db.query(Task)
        .filter(Task.run_id == payload.run_id, Task.role == payload.role)
        .first()
    )
    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"Task '{payload.role}' not found in run {payload.run_id}",
        )

    task.status = payload.status
    if payload.started_at is not None:
        task.started_at = payload.started_at
    if payload.finished_at is not None:
        task.finished_at = payload.finished_at
    if payload.duration_s is not None:
        task.duration_s = payload.duration_s
    if payload.error is not None:
        task.error = payload.error

    # Auto-close run when all tasks are terminal
    run = db.query(Run).filter(Run.id == payload.run_id).first()
    if run:
        all_tasks = db.query(Task).filter(Task.run_id == payload.run_id).all()
        statuses  = [t.status for t in all_tasks]
        if all(s in ("done", "failed") for s in statuses):
            run.status      = "failed" if "failed" in statuses else "done"
            run.finished_at = datetime.utcnow()

    db.commit()
    db.refresh(task)
    return task
