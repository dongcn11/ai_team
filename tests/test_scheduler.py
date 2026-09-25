"""Lịch chạy định kỳ theo dự án: tính mốc, chạy bù, chống bắn trùng, quét tài liệu.

Bám đúng "Bộ test tối thiểu" trong
_bmad-output/implementation-artifacts/spec-project-schedules.md

Chạy:  python -m pytest tests/test_scheduler.py -q

Nguyên tắc: KHÔNG `sleep`, không chờ đồng hồ thật. Mọi test truyền `now` vào
`scheduler.tick(now=...)` — trên máy CI tải nặng, chờ thời gian thật khiến hành
vi ĐÚNG vẫn fail ngẫu nhiên.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "dashboard" / "api"

# DATABASE_URL phải được đặt TRƯỚC khi import `database` — module đó tạo engine
# ngay lúc import và sẽ thử nối Postgres 15 lần nếu không có biến này.
_TMP = Path(tempfile.mkdtemp(prefix="sched-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["SCHEDULER_DRY_RUN"] = "0"      # scheduler đọc cờ này lúc import
os.environ["SCHEDULER_GRACE_S"] = "300"
os.environ["SCHEDULER_CATCHUP_WINDOW_H"] = "24"

sys.path.insert(0, str(API_DIR))

import database  # noqa: E402
import doc_scan  # noqa: E402
import models  # noqa: E402
import scheduler  # noqa: E402

models.Base.metadata.create_all(bind=database.engine)

TZ = "Asia/Ho_Chi_Minh"
SLUG = "acme"


# --------------------------------------------------------------------------- #
# Hạ tầng test
# --------------------------------------------------------------------------- #

@pytest.fixture
def clients_dir(tmp_path, monkeypatch):
    """Thư mục tài liệu giả, thay cho clients/ thật."""
    root = tmp_path / "clients"
    (root / SLUG).mkdir(parents=True)
    (root / SLUG / "prd.md").write_text("# PRD\nnội dung ban đầu\n", encoding="utf-8")
    monkeypatch.setattr(doc_scan, "CLIENTS_DIR", str(root))
    return root


@pytest.fixture
def db(clients_dir):
    """Session sạch cho từng test."""
    s = database.SessionLocal()
    for model in (models.DocSnapshot, models.RunJob, models.WorkflowRun, models.Schedule,
                  models.Workflow, models.Project):
        s.query(model).delete()
    s.commit()
    yield s
    s.close()


@pytest.fixture
def project(db):
    p = models.Project(name="Acme", client_folder=SLUG)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture
def workflow(db, project):
    w = models.Workflow(project_id=project.id, name="Cập nhật theo tài liệu",
                        definition={"nodes": [{"id": "n1", "type": "action.task"}], "edges": []})
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


def _mk_schedule(db, project, **kw):
    wf = db.query(models.Workflow).filter(models.Workflow.project_id == project.id).first()
    defaults = dict(
        project_id=project.id, name="Quét tài liệu 6h",
        cron_expression="0 6 * * *", timezone=TZ, enabled=True,
        job_kind="scan_docs", misfire_policy="catchup_once",
        concurrency_policy="forbid", on_change="run_workflow", jitter_s=0,
        workflow_id=wf.id if wf else None,
    )
    defaults.update(kw)
    s = models.Schedule(**defaults)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _seed_snapshot(db, project):
    """Ghi ảnh chụp hiện tại, để test không rơi vào nhánh 'lần quét đầu'."""
    snap = doc_scan.snapshot_dir(doc_scan.docs_path(project.client_folder))
    for rel, sha in snap.items():
        db.add(models.DocSnapshot(project_id=project.id, rel_path=rel, sha256=sha))
    db.commit()


def _jobs(db, schedule_id=None):
    """Workflow run do lịch tạo ra (lịch chạy workflow, không còn đẻ run_job pipeline)."""
    q = db.query(models.WorkflowRun)
    if schedule_id is not None:
        q = q.filter(models.WorkflowRun.schedule_id == schedule_id)
    return q.all()


def _utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# 1. Tính mốc chạy
# --------------------------------------------------------------------------- #

def test_next_fire_respects_project_timezone():
    """'0 6 * * *' ở Asia/Ho_Chi_Minh phải là 06:00 GIỜ VN, không phải giờ UTC."""
    after = _utc(2026, 9, 22, 0, 0)           # 07:00 giờ VN → đã qua 6h sáng nay
    nxt = scheduler.next_fire("0 6 * * *", TZ, after)

    assert nxt.tzinfo is not None
    from zoneinfo import ZoneInfo
    local = nxt.astimezone(ZoneInfo(TZ))
    assert (local.hour, local.minute) == (6, 0)
    assert local.date() == datetime(2026, 9, 23).date()   # sáng hôm sau
    assert nxt == _utc(2026, 9, 22, 23, 0)                # VN = UTC+7


def test_preview_returns_consecutive_daily_runs():
    runs = scheduler.preview("0 6 * * *", TZ, count=5, after=_utc(2026, 9, 22, 0, 0))
    assert len(runs) == 5
    assert all((r.hour, r.minute) == (6, 0) for r in runs)
    for a, b in zip(runs, runs[1:]):
        assert (b - a) == timedelta(days=1)


def test_validate_rejects_bad_cron_and_timezone():
    with pytest.raises(ValueError):
        scheduler.validate("khong-phai-cron", TZ)
    with pytest.raises(ValueError):
        scheduler.validate("0 6 * * *", "Asia/Khong_Ton_Tai")


# --------------------------------------------------------------------------- #
# 2-3. Lỡ nhịp khi máy tắt
# --------------------------------------------------------------------------- #

def test_catchup_once_creates_exactly_one_job_after_three_days_off(db, project, workflow):
    """Máy tắt 3 ngày → tạo ĐÚNG 1 job, không phải 3."""
    sched = _mk_schedule(db, project, misfire_policy="catchup_once")
    sched.next_run_at = scheduler._naive(_utc(2026, 9, 22, 23, 0))   # 3 ngày trước
    db.commit()
    _seed_snapshot(db, project)
    (doc_scan.docs_path(SLUG) / "prd.md").write_text("# PRD\nĐÃ SỬA\n", encoding="utf-8")

    now = _utc(2026, 9, 26, 0, 0)        # 07:00 VN — 6h sáng nay đã trôi qua 1 tiếng
    assert scheduler.tick(now=now) == 1

    db.expire_all()
    assert len(_jobs(db, sched.id)) == 1
    s = db.get(models.Schedule, sched.id)
    assert s.last_status == "fired"
    assert scheduler._aware(s.next_run_at) > now      # mốc đã tiến về tương lai


def test_skip_policy_creates_no_job_but_still_advances(db, project, workflow):
    sched = _mk_schedule(db, project, misfire_policy="skip")
    sched.next_run_at = scheduler._naive(_utc(2026, 9, 22, 23, 0))
    db.commit()
    _seed_snapshot(db, project)
    (doc_scan.docs_path(SLUG) / "prd.md").write_text("# PRD\nĐÃ SỬA\n", encoding="utf-8")

    now = _utc(2026, 9, 26, 0, 0)
    scheduler.tick(now=now)

    db.expire_all()
    assert _jobs(db, sched.id) == []
    s = db.get(models.Schedule, sched.id)
    assert s.last_status == "skipped"
    assert scheduler._aware(s.next_run_at) > now


def test_missed_beyond_catchup_window_is_not_run(db, project, workflow):
    """Lịch hằng tháng, máy tắt cả tháng → mốc lỡ nằm ngoài cửa sổ 24h → bỏ."""
    sched = _mk_schedule(db, project, cron_expression="0 6 1 * *")   # 6h sáng mùng 1
    sched.next_run_at = scheduler._naive(_utc(2026, 7, 31, 23, 0))
    db.commit()
    _seed_snapshot(db, project)
    (doc_scan.docs_path(SLUG) / "prd.md").write_text("# PRD\nĐÃ SỬA\n", encoding="utf-8")

    now = _utc(2026, 9, 20, 0, 0)        # mùng 1 gần nhất đã 19 ngày trước
    scheduler.tick(now=now)

    db.expire_all()
    assert _jobs(db, sched.id) == []
    assert db.get(models.Schedule, sched.id).last_status == "missed"


# --------------------------------------------------------------------------- #
# 4. Chống bắn trùng
# --------------------------------------------------------------------------- #

def test_same_fire_time_twice_yields_one_job(db, project, workflow):
    """Mô phỏng uvicorn --reload chạy lại tick cho cùng một mốc.

    UNIQUE (schedule_id, fire_time) là thứ DUY NHẤT chặn trùng — không phải một
    câu SELECT kiểm tra trước.
    """
    sched = _mk_schedule(db, project)
    sched.next_run_at = scheduler._naive(_utc(2026, 9, 25, 23, 0))
    db.commit()
    _seed_snapshot(db, project)
    (doc_scan.docs_path(SLUG) / "prd.md").write_text("# PRD\nĐÃ SỬA\n", encoding="utf-8")

    now = _utc(2026, 9, 26, 0, 0)
    scheduler.tick(now=now)

    # Tick lại đúng mốc đó: đẩy next_run_at về quá khứ như lúc vừa restart.
    db.expire_all()
    s = db.get(models.Schedule, sched.id)
    s.next_run_at = scheduler._naive(_utc(2026, 9, 25, 23, 0))
    db.commit()
    scheduler.tick(now=now)

    db.expire_all()
    jobs = _jobs(db, sched.id)
    assert len(jobs) == 1, f"phải đúng 1 job cho 1 mốc, đang có {len(jobs)}"
    assert jobs[0].schedule_id == sched.id
    assert jobs[0].workflow_id == workflow.id
    assert jobs[0].status == "running"


# --------------------------------------------------------------------------- #
# 5. Chống dồn ứ (worker chạy tuần tự)
# --------------------------------------------------------------------------- #

def test_forbid_skips_when_project_workflow_running(db, project, workflow):
    """Workflow của dự án đang chạy dở cũng tính là bận."""
    sched = _mk_schedule(db, project, concurrency_policy="forbid")
    sched.next_run_at = scheduler._naive(_utc(2026, 9, 25, 23, 0))
    db.add(models.WorkflowRun(workflow_id=workflow.id, status="running"))
    db.commit()
    _seed_snapshot(db, project)
    (doc_scan.docs_path(SLUG) / "prd.md").write_text("# PRD\nĐÃ SỬA\n", encoding="utf-8")

    scheduler.tick(now=_utc(2026, 9, 26, 0, 0))

    db.expire_all()
    assert _jobs(db, sched.id) == []
    assert db.get(models.Schedule, sched.id).last_status == "skipped"


def test_missing_workflow_is_error_not_run(db, project):
    """Chọn chạy workflow mà workflow đã bị xoá → báo lỗi, không tạo gì."""
    sched = _mk_schedule(db, project, workflow_id=None)
    sched.next_run_at = scheduler._naive(_utc(2026, 9, 25, 23, 0))
    db.commit()
    _seed_snapshot(db, project)
    (doc_scan.docs_path(SLUG) / "prd.md").write_text("# PRD\nĐÃ SỬA\n", encoding="utf-8")

    scheduler.tick(now=_utc(2026, 9, 26, 0, 0))

    db.expire_all()
    assert _jobs(db) == []
    s = db.get(models.Schedule, sched.id)
    assert s.last_status == "error"
    assert "chưa chọn workflow" in (s.last_detail or "")


@pytest.mark.parametrize("busy_status", ["queued", "running"])
def test_forbid_skips_when_project_already_busy(db, project, workflow, busy_status):
    sched = _mk_schedule(db, project, concurrency_policy="forbid")
    sched.next_run_at = scheduler._naive(_utc(2026, 9, 25, 23, 0))
    db.add(models.RunJob(client_folder=SLUG, project_id=project.id, status=busy_status))
    db.commit()
    _seed_snapshot(db, project)
    (doc_scan.docs_path(SLUG) / "prd.md").write_text("# PRD\nĐÃ SỬA\n", encoding="utf-8")

    now = _utc(2026, 9, 26, 0, 0)
    scheduler.tick(now=now)

    db.expire_all()
    assert _jobs(db, sched.id) == []
    s = db.get(models.Schedule, sched.id)
    assert s.last_status == "skipped"
    assert "forbid" in (s.last_detail or "")
    assert scheduler._aware(s.next_run_at) > now


# --------------------------------------------------------------------------- #
# 6. Quét tài liệu
# --------------------------------------------------------------------------- #

def test_no_change_creates_no_job(db, project, workflow):
    """Tài liệu không đổi → KHÔNG đánh thức pipeline. Đây là chỗ tiết kiệm token."""
    sched = _mk_schedule(db, project)
    sched.next_run_at = scheduler._naive(_utc(2026, 9, 25, 23, 0))
    db.commit()
    _seed_snapshot(db, project)          # ảnh chụp khớp hệt nội dung hiện tại

    scheduler.tick(now=_utc(2026, 9, 26, 0, 0))

    db.expire_all()
    assert _jobs(db, sched.id) == []
    assert db.get(models.Schedule, sched.id).last_status == "no_change"


def test_first_scan_only_stores_baseline(db, project, workflow):
    """Lần quét đầu chưa có gì để so — lưu ảnh chụp, đừng báo 'thêm N file'."""
    sched = _mk_schedule(db, project)
    sched.next_run_at = scheduler._naive(_utc(2026, 9, 25, 23, 0))
    db.commit()

    scheduler.tick(now=_utc(2026, 9, 26, 0, 0))

    db.expire_all()
    assert _jobs(db, sched.id) == []
    assert db.get(models.Schedule, sched.id).last_status == "no_change"
    assert db.query(models.DocSnapshot).filter(
        models.DocSnapshot.project_id == project.id).count() == 1


def test_notify_only_does_not_create_job(db, project, workflow):
    sched = _mk_schedule(db, project, on_change="notify")
    sched.next_run_at = scheduler._naive(_utc(2026, 9, 25, 23, 0))
    db.commit()
    _seed_snapshot(db, project)
    (doc_scan.docs_path(SLUG) / "prd.md").write_text("# PRD\nĐÃ SỬA\n", encoding="utf-8")

    scheduler.tick(now=_utc(2026, 9, 26, 0, 0))

    db.expire_all()
    assert _jobs(db, sched.id) == []
    assert db.get(models.Schedule, sched.id).last_status == "fired"


def test_missing_docs_dir_is_error_not_crash(db):
    """Project chưa có thư mục tài liệu không được làm chết vòng tick."""
    p = models.Project(name="Trống", client_folder="khong-co-thu-muc")
    db.add(p)
    db.commit()
    db.refresh(p)
    sched = _mk_schedule(db, p)
    sched.next_run_at = scheduler._naive(_utc(2026, 9, 25, 23, 0))
    db.commit()

    assert scheduler.tick(now=_utc(2026, 9, 26, 0, 0)) == 1

    db.expire_all()
    s = db.get(models.Schedule, sched.id)
    assert s.last_status == "error"
    assert scheduler._aware(s.next_run_at) > _utc(2026, 9, 26, 0, 0)


def test_disabled_schedule_is_ignored(db, project, workflow):
    sched = _mk_schedule(db, project, enabled=False)
    sched.next_run_at = scheduler._naive(_utc(2026, 9, 25, 23, 0))
    db.commit()

    assert scheduler.tick(now=_utc(2026, 9, 26, 0, 0)) == 0


# --------------------------------------------------------------------------- #
# doc_scan thuần
# --------------------------------------------------------------------------- #

def test_snapshot_and_diff(tmp_path):
    root = tmp_path / "docs"
    (root / "sub").mkdir(parents=True)
    (root / "a.md").write_text("A", encoding="utf-8")
    (root / "sub" / "b.md").write_text("B", encoding="utf-8")
    (root / "ảnh.png").write_bytes(b"\x89PNG")          # không phải tài liệu
    (root / ".git").mkdir()
    (root / ".git" / "c.md").write_text("C", encoding="utf-8")   # phải bị bỏ qua

    snap = doc_scan.snapshot_dir(root)
    assert set(snap) == {"a.md", "sub/b.md"}

    (root / "a.md").write_text("A sửa rồi", encoding="utf-8")
    (root / "new.md").write_text("mới", encoding="utf-8")
    (root / "sub" / "b.md").unlink()
    d = doc_scan.diff(snap, doc_scan.snapshot_dir(root))

    assert d == {"added": ["new.md"], "removed": ["sub/b.md"], "changed": ["a.md"]}
    assert doc_scan.has_changes(d)
    assert not doc_scan.has_changes(doc_scan.diff(snap, snap))


def test_output_dir_is_excluded(tmp_path):
    """Hồi quy: code do pipeline sinh ra nằm trong `output/` KHÔNG được tính là
    tài liệu — nếu tính, mỗi lần chạy pipeline lại kích hoạt lần chạy kế tiếp,
    thành vòng lặp tự nuôi. Phát hiện trên dữ liệu thật của dự án `booking`."""
    root = tmp_path / "docs"
    (root / "output" / "backend" / "be1").mkdir(parents=True)
    (root / "vendor").mkdir()
    (root / "prd.md").write_text("tài liệu thật", encoding="utf-8")
    (root / "output" / "backend" / "be1" / "composer.json").write_text("{}", encoding="utf-8")
    (root / "output" / "README.md").write_text("do pipeline sinh", encoding="utf-8")
    (root / "vendor" / "x.json").write_text("{}", encoding="utf-8")
    # routers/workflows.py ghi 1 file .md vào _tasks/ cho mỗi node mỗi lần chạy.
    (root / "_tasks").mkdir()
    (root / "_tasks" / "wf13_run22_node_1.md").write_text("status: done", encoding="utf-8")

    assert set(doc_scan.snapshot_dir(root)) == {"prd.md"}


def test_config_files_are_excluded(tmp_path):
    """settings.local.toml giữ credential — đổi token không phải là "tài liệu
    thay đổi", càng không đáng để chạy cả pipeline."""
    root = tmp_path / "docs"
    root.mkdir()
    (root / "settings.toml").write_text("[project]", encoding="utf-8")
    (root / "settings.local.toml").write_text("token='bi-mat'", encoding="utf-8")
    (root / "mcp.json").write_text("{}", encoding="utf-8")
    (root / "prd.md").write_text("tài liệu thật", encoding="utf-8")

    assert set(doc_scan.snapshot_dir(root)) == {"prd.md"}


def test_snapshot_missing_dir_raises(tmp_path):
    with pytest.raises(doc_scan.DocScanError):
        doc_scan.snapshot_dir(tmp_path / "khong-ton-tai")
