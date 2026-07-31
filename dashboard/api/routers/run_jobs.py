"""
Run Jobs — hàng đợi trigger pipeline
====================================
Dashboard bấm ▶ Run → tạo job `queued`. worker.py (chạy trên host) gọi
/claim để lấy job cũ nhất, chạy `python main.py`, rồi báo /complete.

Thiết kế tuần tự: /claim không trả job mới khi đang có job `running` →
đảm bảo 1 job/lần dù worker restart giữa chừng (tránh xung đột git/thư mục).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from datetime import datetime, timedelta

from database import get_db
from models import RunJob, Project, ProjectTask
from schemas import RunJobCreate, RunJobComplete, RunJobOut

router = APIRouter()

# Feature đang dang dở → sẽ được orchestrator mark 'done' sau khi pipeline xong
_PENDING_FEATURE_STATUSES = ("todo", "in_progress", "review")


@router.post("", response_model=RunJobOut)
def enqueue(payload: RunJobCreate, db: Session = Depends(get_db)):
    """Đưa 1 project vào hàng đợi chạy. Tự resolve project_id + feature_ids
    để orchestrator có thể đánh dấu feature 'done' khi hoàn thành."""
    folder = payload.client_folder.strip()
    if not folder:
        raise HTTPException(status_code=400, detail="client_folder is required")

    project_id: Optional[int] = None
    feature_ids = ""
    proj = db.query(Project).filter(Project.client_folder == folder).first()
    if proj:
        project_id = proj.id
        ids = [str(t.id) for t in proj.tasks if t.status in _PENDING_FEATURE_STATUSES]
        feature_ids = ",".join(ids)

    job = RunJob(
        client_folder=folder,
        project_id=project_id,
        profile=payload.profile,
        feature_ids=feature_ids,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("", response_model=List[RunJobOut])
def list_jobs(
    client_folder: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    q = db.query(RunJob).order_by(desc(RunJob.id))
    if client_folder:
        q = q.filter(RunJob.client_folder == client_folder)
    if status:
        q = q.filter(RunJob.status == status)
    return q.limit(limit).all()


@router.post("/claim", response_model=Optional[RunJobOut])
def claim_job(db: Session = Depends(get_db)):
    """worker gọi đây. Trả job cũ nhất đang `queued` và đánh dấu `running`.
    Trả null nếu hàng đợi rỗng HOẶC đã có job đang chạy (giữ tuần tự).
    Job bị kẹt ở running quá 2 giờ (worker crash) sẽ tự động reset thành failed."""
    cutoff = datetime.utcnow() - timedelta(hours=2)
    stuck = db.query(RunJob).filter(
        RunJob.status == "running",
        RunJob.started_at < cutoff,
    ).all()
    for s in stuck:
        s.status = "failed"
        s.error = "Timeout: worker không báo complete sau 2 giờ (có thể crash)"
        s.finished_at = datetime.utcnow()
    if stuck:
        db.commit()

    running = db.query(RunJob).filter(RunJob.status == "running").first()
    if running:
        return None

    q = db.query(RunJob).filter(RunJob.status == "queued").order_by(RunJob.id)
    # skip_locked: an toàn nếu sau này có >1 worker; vô hại với 1 worker
    try:
        job = q.with_for_update(skip_locked=True).first()
    except Exception:
        job = q.first()  # sqlite/dev fallback
    if not job:
        return None

    job.status = "running"
    job.started_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/complete", response_model=RunJobOut)
def complete_job(job_id: int, payload: RunJobComplete, db: Session = Depends(get_db)):
    job = db.query(RunJob).filter(RunJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if payload.status not in ("done", "failed"):
        raise HTTPException(status_code=400, detail="status phải là 'done' hoặc 'failed'")
    job.status = payload.status
    job.error = (payload.error or "")[:1000] or None
    job.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/cancel", response_model=RunJobOut)
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(RunJob).filter(RunJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "queued":
        raise HTTPException(status_code=400, detail="Chỉ huỷ được job đang chờ (queued)")
    job.status = "canceled"
    job.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job
