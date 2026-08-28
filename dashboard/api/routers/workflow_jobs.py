"""
Workflow Step Jobs — hàng đợi chạy 1 bước workflow bằng Claude headless
======================================================================
Workflow bật `auto_run` → mỗi khi hệ thống soạn xong file task cho 1 bước,
nó tạo job `queued` ở đây. `worker.py` (chạy TRÊN MÁY BẠN) poll /claim, chạy

    claude -p "<prompt>"

trong thư mục repo, rồi báo /complete. Claude sửa file task (`status: done`)
→ vòng poll nền của workflow đọc file và mở bước kế tiếp như khi bạn chạy tay.

Vì sao phải vòng qua worker: API nằm trong container — không có CLI `claude`,
không có repo thật, không có phiên đăng nhập của bạn.

Ranh giới với chính sách "pipeline không dùng Claude Code" (README): chốt đó
chặn pipeline `ai_team/` — chạy nền nhiều project, agent song song, không ai
giám sát. Hàng đợi này thì ngược lại: phải bật tay từng workflow, chạy trên
máy của chính người bấm, TUẦN TỰ 1 bước/lần. Đừng nới 2 giới hạn đó.
"""

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from models import WorkflowStepJob, WorkflowRun
from schemas import WorkflowStepJobOut, WorkflowStepJobComplete
import worker_heartbeat

router = APIRouter()

# Worker chết giữa chừng → job kẹt 'running' mãi sẽ khoá cả hàng đợi (claim giữ
# tuần tự). Quá ngưỡng này thì coi như hỏng và giải phóng hàng đợi.
_STUCK_AFTER = timedelta(hours=1)


@router.get("", response_model=List[WorkflowStepJobOut])
def list_jobs(run_id: Optional[int] = None, status: Optional[str] = None,
              limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(WorkflowStepJob).order_by(desc(WorkflowStepJob.id))
    if run_id is not None:
        q = q.filter(WorkflowStepJob.run_id == run_id)
    if status:
        q = q.filter(WorkflowStepJob.status == status)
    return q.limit(limit).all()


@router.get("/worker")
def worker_status():
    """Worker trên host có đang hỏi việc không — UI dùng để phân biệt
    "chưa ai chạy worker.py" với "worker đang bận". Xem worker_heartbeat.py."""
    return worker_heartbeat.status()


@router.post("/claim", response_model=Optional[WorkflowStepJobOut])
def claim_job(db: Session = Depends(get_db)):
    """worker gọi đây. Trả job `queued` cũ nhất và đánh dấu `running`.
    Trả null khi hàng đợi rỗng HOẶC đang có job chạy — 1 bước/lần, cố ý."""
    worker_heartbeat.touch()
    cutoff = datetime.utcnow() - _STUCK_AFTER
    stuck = (db.query(WorkflowStepJob)
               .filter(WorkflowStepJob.status == "running",
                       WorkflowStepJob.started_at < cutoff).all())
    for job in stuck:
        job.status = "failed"
        job.error = "Timeout: worker không báo complete sau 1 giờ (có thể đã crash)"
        job.finished_at = datetime.utcnow()
    if stuck:
        db.commit()

    if db.query(WorkflowStepJob).filter(WorkflowStepJob.status == "running").first():
        return None

    q = db.query(WorkflowStepJob).filter(WorkflowStepJob.status == "queued").order_by(WorkflowStepJob.id)
    try:
        job = q.with_for_update(skip_locked=True).first()
    except Exception:
        job = q.first()          # sqlite/dev fallback
    if not job:
        return None

    # Run bị huỷ/kết thúc trong lúc job còn nằm chờ → bỏ job, đừng chạy nữa
    run = db.query(WorkflowRun).filter(WorkflowRun.id == job.run_id).first()
    if run is None or run.status != "running":
        job.status = "canceled"
        job.error = "Lần chạy đã kết thúc hoặc bị huỷ trước khi worker nhận job"
        job.finished_at = datetime.utcnow()
        db.commit()
        return None

    job.status = "running"
    job.started_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/complete", response_model=WorkflowStepJobOut)
def complete_job(job_id: int, payload: WorkflowStepJobComplete, db: Session = Depends(get_db)):
    job = db.query(WorkflowStepJob).filter(WorkflowStepJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if payload.status not in ("done", "failed"):
        raise HTTPException(status_code=400, detail="status phải là 'done' hoặc 'failed'")
    job.status = payload.status
    job.output = (payload.output or "")[:8000] or None
    job.error = (payload.error or "")[:2000] or None
    job.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/retry", response_model=WorkflowStepJobOut)
def retry_job(job_id: int, db: Session = Depends(get_db)):
    """Chạy lại 1 bước đã lỗi — file task vẫn còn nên chỉ cần xếp lại hàng đợi."""
    job = db.query(WorkflowStepJob).filter(WorkflowStepJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("failed", "canceled"):
        raise HTTPException(status_code=400, detail=f"Job đang '{job.status}' — chỉ chạy lại được job lỗi/đã huỷ")
    run = db.query(WorkflowRun).filter(WorkflowRun.id == job.run_id).first()
    if run is None or run.status != "running":
        raise HTTPException(status_code=400, detail="Lần chạy đã kết thúc — không xếp lại được")
    job.status = "queued"
    job.output = None
    job.error = None
    job.started_at = None
    job.finished_at = None
    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/cancel", response_model=WorkflowStepJobOut)
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    """Bỏ 1 job còn nằm chờ. Job đang chạy thì phải dừng ở terminal worker —
    API không giết được tiến trình trên máy bạn."""
    job = db.query(WorkflowStepJob).filter(WorkflowStepJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "queued":
        raise HTTPException(status_code=400, detail="Chỉ huỷ được job đang chờ (queued)")
    job.status = "canceled"
    job.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job
