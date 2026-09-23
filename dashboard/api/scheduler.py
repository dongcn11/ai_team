"""
Scheduler — "đồng hồ" còn thiếu
===============================
Đọc bảng `schedules`, tới giờ thì quét tài liệu dự án, và CHỈ KHI tài liệu thực
sự đổi mới chèn một dòng vào `run_jobs`.

Vì sao không dùng APScheduler: `run_jobs` đã là hàng đợi và `worker.py` đã là
executor. Một framework scheduler đầy đủ sẽ dựng SONG SONG một job store và một
executor thứ hai chồng lên thứ đã có — hai nguồn sự thật cho cùng một khái niệm.
Thứ còn thiếu chỉ là schedule store (bảng `schedules`) và tick coordinator (file
này). Chi tiết: _bmad-output/planning-artifacts/research/technical-per-project-
cron-scheduler-research-2026-09-22.md

`worker.py` KHÔNG bị sửa gì: nó vẫn `POST /api/run-jobs/claim` như trước.

Quy ước thời gian — đọc kỹ trước khi sửa:
  * Cột DateTime trong DB là naive (theo phần còn lại của schema) và LUÔN là UTC.
  * Mọi phép tính dùng datetime CÓ timezone; ghi xuống DB thì bỏ tzinfo (`_naive`).
  * Không bao giờ dùng `datetime.utcnow()` — nó trả naive và là nguồn lỗi DST kinh điển.
  * Không tự cộng `timedelta(days=1)` để nhảy ngày: cộng đúng 24 giờ, không giữ
    nguyên giờ đồng hồ khi đổi DST. Luôn đi qua croniter.
"""
from __future__ import annotations

import os
import threading
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import doc_scan
from database import SessionLocal
from models import ChatBot, DocSnapshot, Project, RunJob, Schedule

# Tick chỉ truy vấn 1 câu có index → 60s là đủ dày mà không tốn gì.
TICK_S          = int(os.getenv("SCHEDULER_TICK_S", "60"))
# Trễ trong khoảng này vẫn coi là "đúng giờ" (tick không thể chính xác từng giây).
GRACE_S         = int(os.getenv("SCHEDULER_GRACE_S", "300"))
# Chặn trên của việc chạy bù: máy tắt quá lâu thì đừng đánh thức pipeline nữa.
CATCHUP_WINDOW_H = int(os.getenv("SCHEDULER_CATCHUP_WINDOW_H", "24"))
# MẶC ĐỊNH BẬT. Tick chạy đủ và log đủ nhưng không INSERT, không thông báo.
# Tắt bằng SCHEDULER_DRY_RUN=0 sau khi đã soát log ít nhất một chu kỳ ngày đêm.
DRY_RUN         = os.getenv("SCHEDULER_DRY_RUN", "1") not in ("0", "false", "False", "")
ENABLED         = os.getenv("SCHEDULER_ENABLED", "1") not in ("0", "false", "False", "")

_BUSY_STATUSES = ("queued", "running")


def _log(msg: str) -> None:
    print(f"[scheduler] {msg}", flush=True)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _naive(dt: datetime) -> datetime:
    """datetime có tz -> naive UTC, để ghi vào cột DateTime của schema hiện tại."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Cột DB (naive, UTC) -> datetime có tz."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Tính mốc chạy
# --------------------------------------------------------------------------- #

def validate(cron_expression: str, tz_name: str) -> None:
    """Ném ValueError nếu cron hoặc timezone sai. Router gọi hàm này để trả 422."""
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise ValueError(f"Timezone không hợp lệ: {tz_name!r}")
    if not croniter.is_valid(cron_expression):
        raise ValueError(f"Biểu thức cron không hợp lệ: {cron_expression!r}")


def next_fire(cron_expression: str, tz_name: str, after: datetime) -> datetime:
    """Mốc chạy đầu tiên SAU `after`. Trả datetime có tz, chuẩn UTC.

    croniter được khởi tạo bằng giờ ĐỊA PHƯƠNG có tzinfo — đó là cách duy nhất để
    "6h sáng" nghĩa là 6h sáng ở múi giờ người dùng chọn, không phải giờ máy chủ.
    """
    validate(cron_expression, tz_name)
    tz = ZoneInfo(tz_name)
    local = after.astimezone(tz)
    return croniter(cron_expression, local).get_next(datetime).astimezone(timezone.utc)


def prev_fire(cron_expression: str, tz_name: str, before: datetime) -> datetime:
    """Mốc chạy gần nhất TRƯỚC (hoặc bằng) `before`. Trả datetime có tz, chuẩn UTC."""
    validate(cron_expression, tz_name)
    tz = ZoneInfo(tz_name)
    local = before.astimezone(tz)
    return croniter(cron_expression, local).get_prev(datetime).astimezone(timezone.utc)


def preview(cron_expression: str, tz_name: str, count: int = 5,
            after: Optional[datetime] = None) -> list[datetime]:
    """N mốc chạy kế tiếp, theo giờ địa phương của lịch — để người dùng TỰ kiểm
    chứng biểu thức cron trước khi lưu, thay vì đợi tới 6h sáng mới biết sai."""
    validate(cron_expression, tz_name)
    tz = ZoneInfo(tz_name)
    it = croniter(cron_expression, (after or _utcnow()).astimezone(tz))
    return [it.get_next(datetime) for _ in range(max(1, min(count, 20)))]


# --------------------------------------------------------------------------- #
# Thông báo
# --------------------------------------------------------------------------- #

def _pick_bot(db: Session, client_folder: Optional[str]) -> Optional[ChatBot]:
    """Bot khớp HẸP NHẤT thắng — bot của đúng dự án hơn bot chung (xem docstring
    models.ChatBot). `chat_router.notify_run` KHÔNG dùng được ở đây: nó trả lời
    đúng cuộc chat đã kích hoạt một WorkflowRun, mà lịch thì không có chat nguồn.
    """
    bots = db.query(ChatBot).filter(ChatBot.enabled.is_(True), ChatBot.chats != "").all()
    scoped = [b for b in bots if client_folder and b.client_folder == client_folder]
    general = [b for b in bots if not b.client_folder]
    picked = scoped or general
    return picked[0] if picked else None


def _notify(client_folder: Optional[str], text: str) -> None:
    """Gửi nền. Mạng chậm không được làm trễ nhịp tick."""
    def run() -> None:
        db = SessionLocal()
        try:
            import chat_router
            bot = _pick_bot(db, client_folder)
            if not bot:
                return                     # chưa khai bot nào — im lặng, không phải lỗi
            # Nội dung là văn bản thuần, không markup → không cần fmt_for(bot).
            for chat_id in [c.strip() for c in (bot.chats or "").split(",") if c.strip()]:
                chat_router.send_to(db, bot, chat_id, text, thread=None)
        except Exception as e:
            _log(f"không gửi được thông báo: {e}")
        finally:
            db.close()

    threading.Thread(target=run, daemon=True).start()


# --------------------------------------------------------------------------- #
# Tick
# --------------------------------------------------------------------------- #

def _busy(db: Session, project_id: Optional[int]) -> bool:
    """Project còn job đang chờ/đang chạy? Worker chạy TUẦN TỰ tuyệt đối
    (run_jobs.py chặn claim khi có job running) nên chất chồng chỉ làm dồn ứ."""
    if project_id is None:
        return False
    return db.query(RunJob.id).filter(
        RunJob.project_id == project_id,
        RunJob.status.in_(_BUSY_STATUSES),
    ).first() is not None


def _insert_job(db: Session, proj: Project, sched: Schedule, fire: datetime) -> bool:
    """Chèn job cho đúng một mốc lịch. Trả True nếu đã chèn, False nếu bị chặn trùng.

    Chống trùng do DATABASE phân xử qua UNIQUE (schedule_id, fire_time). Kiểu
    "SELECT xem có chưa rồi mới INSERT" KHÔNG an toàn: hai tiến trình đều có thể
    thấy "chưa có" trước khi bên nào kịp ghi.
    """
    values = dict(
        client_folder=proj.client_folder or "",
        project_id=proj.id,
        status="queued",
        source="schedule",
        schedule_id=sched.id,
        fire_time=_naive(fire),
    )

    if db.bind is not None and db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = (pg_insert(RunJob.__table__)
                .values(**values)
                .on_conflict_do_nothing(constraint="uq_run_jobs_schedule_fire"))
        res = db.execute(stmt)
        return (res.rowcount or 0) > 0

    # sqlite/dev fallback — cùng tinh thần "fallback" của run_jobs.py:99.
    # Savepoint để lần chèn hỏng không kéo đổ cả transaction của tick.
    try:
        with db.begin_nested():
            db.execute(RunJob.__table__.insert().values(**values))
        return True
    except IntegrityError:
        return False


def _advance(sched: Schedule, now: datetime) -> None:
    sched.next_run_at = _naive(next_fire(sched.cron_expression, sched.timezone, now))
    sched.updated_at = _naive(now)
    sched.version = (sched.version or 0) + 1


def _finish(sched: Schedule, now: datetime, status: str, detail: str) -> None:
    sched.last_run_at = _naive(now)
    sched.last_status = status
    sched.last_detail = detail[:1000]
    _advance(sched, now)
    _log(f"#{sched.id} '{sched.name}' -> {status}: {detail}")


def _process(db: Session, sched: Schedule, now: datetime) -> None:
    """Xử lý MỘT lịch đến hạn. Mọi nhánh đều phải kết thúc bằng `_finish` để
    `next_run_at` luôn tiến — không thì lịch kẹt lại và tick nào cũng gặp nó."""
    proj = db.query(Project).filter(Project.id == sched.project_id).first()
    if not proj:
        _finish(sched, now, "error", "Không tìm thấy project")
        return

    # Mốc lịch gần nhất tính tới bây giờ. Dùng mốc này chứ không dùng `now` để
    # `fire_time` ổn định — đó là thứ UNIQUE dựa vào để chặn bắn trùng.
    try:
        fire = prev_fire(sched.cron_expression, sched.timezone, now)
    except ValueError as e:
        _finish(sched, now, "error", str(e))
        return

    lateness = (now - fire).total_seconds()
    if lateness > GRACE_S:
        # Lỡ nhịp — máy tắt, container dừng, hoặc API vừa khởi động lại.
        if sched.misfire_policy == "skip":
            _finish(sched, now, "skipped", f"lỡ {int(lateness // 60)} phút, policy=skip")
            return
        if lateness > CATCHUP_WINDOW_H * 3600:
            _finish(sched, now, "missed",
                    f"lỡ {int(lateness // 3600)} giờ, quá cửa sổ bù {CATCHUP_WINDOW_H}h")
            return

    if sched.concurrency_policy != "allow" and _busy(db, proj.id):
        _finish(sched, now, "skipped", "project còn job queued/running (policy=forbid)")
        return

    # --- Quét tài liệu ------------------------------------------------------
    root = doc_scan.docs_path(proj.client_folder or "")
    try:
        new_snap = doc_scan.snapshot_dir(root)
    except doc_scan.DocScanError as e:
        _finish(sched, now, "error", str(e))
        return

    old_rows = db.query(DocSnapshot).filter(DocSnapshot.project_id == proj.id).all()
    old_snap = {r.rel_path: r.sha256 for r in old_rows}
    first_scan = not old_rows
    changes = doc_scan.diff(old_snap, new_snap)
    summary = doc_scan.summarize(changes)

    if DRY_RUN:
        _finish(sched, now, "dry_run",
                f"[DRY-RUN] mốc {fire.isoformat()} — {summary}"
                + (" (lần quét đầu, chỉ lưu ảnh chụp)" if first_scan else ""))
        return

    # Lưu ảnh chụp mới cho lần sau, kể cả khi không tạo job.
    _save_snapshot(db, proj.id, old_snap, new_snap)

    if first_scan:
        # Lần đầu chưa có gì để so — lưu ảnh chụp rồi thôi, đừng báo "thêm 200 file".
        _finish(sched, now, "no_change", f"lần quét đầu, đã lưu {len(new_snap)} file")
        return

    if not doc_scan.has_changes(changes):
        _finish(sched, now, "no_change", "tài liệu không đổi")
        return

    # --- Có thay đổi thật ---------------------------------------------------
    detail = f"mốc {fire.isoformat()} — {summary}"
    if sched.on_change in ("run_pipeline", "both"):
        if _insert_job(db, proj, sched, fire):
            detail += " → đã tạo run_job"
        else:
            detail += " → job cho mốc này đã tồn tại (UNIQUE chặn trùng)"
    if sched.on_change in ("notify", "both"):
        _notify(proj.client_folder,
                f"📄 [{proj.name}] tài liệu thay đổi ({sched.name}): {summary}")
        detail += " → đã báo chat"

    _finish(sched, now, "fired", detail)


def _save_snapshot(db: Session, project_id: int, old: dict, new: dict) -> None:
    """Đồng bộ bảng doc_snapshots về đúng ảnh chụp mới nhất."""
    for rel in set(old) - set(new):
        db.query(DocSnapshot).filter(
            DocSnapshot.project_id == project_id, DocSnapshot.rel_path == rel,
        ).delete(synchronize_session=False)
    for rel, sha in new.items():
        if old.get(rel) == sha:
            continue
        row = db.query(DocSnapshot).filter(
            DocSnapshot.project_id == project_id, DocSnapshot.rel_path == rel,
        ).first()
        if row:
            row.sha256 = sha
            row.scanned_at = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            db.add(DocSnapshot(project_id=project_id, rel_path=rel, sha256=sha))


def tick(now: Optional[datetime] = None) -> int:
    """Một nhịp. Trả số lịch đã xử lý.

    Hàm này ĐỒNG BỘ và chậm (có hash file) — người gọi phải đẩy sang
    `asyncio.to_thread`, không được chạy thẳng trong event loop của uvicorn.
    Cùng lý do slack_bot/telegram_bot phải nằm ở thread riêng (xem main.py).
    """
    now = now or _utcnow()
    db = SessionLocal()
    handled = 0
    try:
        q = (db.query(Schedule)
               .filter(Schedule.enabled.is_(True),
                       Schedule.next_run_at.isnot(None),
                       Schedule.next_run_at <= _naive(now))
               .order_by(Schedule.next_run_at))
        try:
            # skip_locked: vô hại với 1 tiến trình, an toàn nếu sau này có nhiều.
            due = q.with_for_update(skip_locked=True).all()
        except Exception:
            due = q.all()                  # sqlite/dev fallback (giống run_jobs.py:99)

        for sched in due:
            try:
                _process(db, sched, now)
                handled += 1
            except Exception as e:
                db.rollback()
                _log(f"#{sched.id} lỗi: {e}\n{traceback.format_exc()}")
                try:    # vẫn phải đẩy next_run_at, không thì kẹt vĩnh viễn
                    fresh = db.query(Schedule).filter(Schedule.id == sched.id).first()
                    if fresh:
                        _finish(fresh, now, "error", str(e))
                except Exception:
                    pass
        db.commit()
    finally:
        db.close()
    return handled


def backfill_next_run_at() -> None:
    """Lịch mới tạo (hoặc vừa đổi cron) chưa có `next_run_at` thì tính lần đầu.
    Chạy lúc API khởi động — rẻ, và tránh lịch nằm im mãi vì thiếu mốc."""
    db = SessionLocal()
    try:
        now = _utcnow()
        rows = db.query(Schedule).filter(
            Schedule.enabled.is_(True), Schedule.next_run_at.is_(None)).all()
        for s in rows:
            try:
                s.next_run_at = _naive(next_fire(s.cron_expression, s.timezone, now))
            except ValueError as e:
                s.last_status, s.last_detail = "error", str(e)[:1000]
        if rows:
            db.commit()
            _log(f"đã tính next_run_at cho {len(rows)} lịch")
    finally:
        db.close()
