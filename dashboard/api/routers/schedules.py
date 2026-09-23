"""
Schedules API — lịch chạy định kỳ theo dự án
============================================
CRUD lịch + xem trước mốc chạy + chạy ngay. Việc bắn job thật do vòng tick trong
main.py làm (xem scheduler.py); router này chỉ là đường vào.

Route tĩnh `/preview` khai TRƯỚC `/{schedule_id}` — nếu không FastAPI sẽ cố khớp
"preview" thành một id. Đúng cái bẫy skills.py đã dẫm phải, mcp.py đã ghi lại.

Cron và timezone được validate NGAY tại đây và trả 422 kèm câu giải thích: lịch
sai cú pháp mà lưu được thì tới 6h sáng mới phát hiện, lúc đó không ai ngồi xem.
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import scheduler
from database import get_db
from models import Project, RunJob, Schedule
from schemas import ScheduleIn, ScheduleOut, SchedulePreviewOut

router = APIRouter()


def _validate(body_cron: str, body_tz: str) -> None:
    try:
        scheduler.validate(body_cron, body_tz)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


def _resolve_project(db: Session, project_id: Optional[int], slug: Optional[str]) -> Project:
    """Nhận ID số HOẶC slug thư mục, trả về hàng trong bảng `projects`.

    Vì sao phải có cả hai: `/api/projects` là filesystem-backed — nó liệt kê
    `clients/<slug>/` và trả `id` = TÊN THƯ MỤC, không đọc bảng `projects`. Nên
    giao diện chỉ cầm slug (xem ProjectMcp nhận `slug`), trong khi `run_jobs`
    và `project_tasks` lại tham chiếu `projects.id` kiểu số. Chuyển đổi đúng
    một chỗ ở đây, thay vì bắt mỗi bên tự đoán.
    """
    if project_id is not None:
        proj = db.query(Project).filter(Project.id == project_id).first()
    elif slug:
        proj = db.query(Project).filter(Project.client_folder == slug).first()
    else:
        raise HTTPException(status_code=400, detail="Cần project_id hoặc slug")
    if not proj:
        raise HTTPException(
            status_code=404,
            detail=f"Project không có trong DB (slug={slug!r}, id={project_id!r}). "
                   "Thư mục trong clients/ chưa chắc đã có hàng tương ứng trong bảng projects.")
    return proj


@router.get("/preview", response_model=SchedulePreviewOut)
def preview(cron: str = Query(..., description="unix-cron 5 trường"),
            tz: str = Query("Asia/Ho_Chi_Minh"),
            count: int = Query(5, ge=1, le=20)):
    """5 mốc chạy kế tiếp theo giờ địa phương. UI gọi mỗi lần người dùng gõ cron."""
    _validate(cron, tz)
    runs = scheduler.preview(cron, tz, count)
    return SchedulePreviewOut(cron_expression=cron, timezone=tz,
                              next_runs=[d.isoformat() for d in runs])


@router.get("", response_model=List[ScheduleOut])
def list_schedules(project_id: Optional[int] = None, slug: Optional[str] = None,
                   db: Session = Depends(get_db)):
    q = db.query(Schedule)
    if project_id is not None or slug:
        q = q.filter(Schedule.project_id == _resolve_project(db, project_id, slug).id)
    return q.order_by(Schedule.id).all()


@router.post("", response_model=ScheduleOut, status_code=201)
def create_schedule(body: ScheduleIn, project_id: Optional[int] = None,
                    slug: Optional[str] = None, db: Session = Depends(get_db)):
    proj = _resolve_project(db, project_id, slug)
    _validate(body.cron_expression, body.timezone)

    sched = Schedule(project_id=proj.id, **body.model_dump())
    # Tính mốc đầu tiên ngay khi tạo — lịch không có next_run_at thì tick không thấy.
    sched.next_run_at = scheduler._naive(
        scheduler.next_fire(body.cron_expression, body.timezone, scheduler._utcnow()))
    db.add(sched)
    db.commit()
    db.refresh(sched)
    return sched


@router.patch("/{schedule_id}", response_model=ScheduleOut)
def update_schedule(schedule_id: int, body: ScheduleIn, db: Session = Depends(get_db)):
    sched = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not sched:
        raise HTTPException(status_code=404, detail="Lịch không tồn tại")
    _validate(body.cron_expression, body.timezone)

    cron_changed = (sched.cron_expression != body.cron_expression
                    or sched.timezone != body.timezone)
    for k, v in body.model_dump().items():
        setattr(sched, k, v)
    # Đổi cron/timezone thì mốc cũ vô nghĩa — tính lại, không giữ mốc của biểu thức cũ.
    if cron_changed or sched.next_run_at is None:
        sched.next_run_at = scheduler._naive(
            scheduler.next_fire(body.cron_expression, body.timezone, scheduler._utcnow()))
    sched.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(sched)
    return sched


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    sched = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not sched:
        raise HTTPException(status_code=404, detail="Lịch không tồn tại")
    db.delete(sched)
    db.commit()


@router.post("/{schedule_id}/run-now", response_model=ScheduleOut)
def run_now(schedule_id: int, db: Session = Depends(get_db)):
    """Đẩy `next_run_at` về quá khứ để nhịp tick kế tiếp xử lý lịch này.

    Cố ý KHÔNG tự chèn run_job ở đây: mọi đường đều phải đi qua cùng một logic
    trong scheduler._process (quét trước, kiểm tra forbid, chống trùng). Hai
    đường tạo job là hai chỗ để lệch nhau.
    """
    sched = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not sched:
        raise HTTPException(status_code=404, detail="Lịch không tồn tại")
    if not sched.enabled:
        raise HTTPException(status_code=400, detail="Lịch đang tắt")
    sched.next_run_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(sched)
    return sched


@router.get("/{schedule_id}/jobs")
def schedule_jobs(schedule_id: int, limit: int = Query(20, ge=1, le=100),
                  db: Session = Depends(get_db)):
    """Các run_job do lịch này sinh ra — để truy vết run tự động về đúng lịch."""
    rows = (db.query(RunJob)
              .filter(RunJob.schedule_id == schedule_id)
              .order_by(RunJob.id.desc()).limit(limit).all())
    return [{"id": r.id, "status": r.status, "fire_time": r.fire_time,
             "created_at": r.created_at, "run_id": r.run_id, "error": r.error}
            for r in rows]
