import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import engine, Base
from routers import (runs, tasks, issues, settings, projects, agents, project_tasks, system,
                     run_jobs, workflows, workflow_jobs, slack_events)
from routers.workflows import poll_running_workflow_runs

Base.metadata.create_all(bind=engine)


# Lightweight in-place migrations — create_all() won't add new columns to existing tables.
def _ensure_column(table: str, column: str, ddl_type: str) -> None:
    dialect = engine.dialect.name
    with engine.connect() as conn:
        if dialect == "sqlite":
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            present = any(r[1] == column for r in rows)
        else:
            res = conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ), {"t": table, "c": column}).first()
            present = res is not None
        if not present:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
            conn.commit()


# (table, column, ddl) — chạy tuần tự, lỗi 1 dòng không chặn các dòng sau.
_COLUMN_MIGRATIONS = [
    ("project_tasks",  "acceptance_criteria", "TEXT"),
    # Mỗi task chọn 1 workflow trong danh sách workflow của project.
    ("project_tasks",  "workflow_id",         "INTEGER"),
    # Run được kích hoạt từ task nào (NULL = chạy tay trong trình soạn workflow).
    ("workflow_runs",  "task_id",             "INTEGER"),
    # Bật/tắt tự chạy từng bước bằng Claude headless (qua worker trên host).
    ("workflows",      "auto_run",            "BOOLEAN DEFAULT FALSE"),
    # Node chọn agent pipeline → job chạy bằng opencode + model của agent đó.
    ("workflow_step_jobs", "tool",              "VARCHAR DEFAULT 'claude'"),
    ("workflow_step_jobs", "model",             "VARCHAR"),
]

for _table, _column, _ddl in _COLUMN_MIGRATIONS:
    try:
        _ensure_column(_table, _column, _ddl)
    except Exception as e:  # best-effort; log so failures are visible in container logs
        print(f"[migrate] {_table}.{_column} column ensure failed: {e}")


def _reconcile_workflow_tables() -> None:
    """Hoà giải bảng workflows/workflow_runs với model hiện tại (PostgreSQL).

    DB đang chạy có thể còn schema workflow đời trước (graph_json / trigger_type /
    log TEXT, name UNIQUE) — create_all() không sửa bảng đã tồn tại nên mọi INSERT
    của trình workflow kéo-thả sẽ hỏng. Ở đây:
      * bổ sung cột model cần (project_id, definition, is_active, node_status),
      * bỏ NOT NULL ở cột chỉ đời cũ mới dùng, để INSERT mới không vướng,
      * cột sai kiểu (log TEXT vs JSON) được đổi tên thành *_legacy rồi tạo lại,
      * bỏ UNIQUE trên workflows.name — mỗi project có danh sách riêng nên trùng
        tên giữa các project là chuyện bình thường.
    Dữ liệu cũ không bị xoá, chỉ đổi tên cột khi lệch kiểu.
    """
    if engine.dialect.name != "postgresql":
        return  # SQLite mới tạo đã đúng schema từ create_all()

    with engine.connect() as conn:
        def columns(table: str) -> dict:
            rows = conn.execute(text(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = :t"
            ), {"t": table}).fetchall()
            return {r[0]: (r[1], r[2]) for r in rows}

        def run(sql: str) -> None:
            conn.execute(text(sql))

        wf = columns("workflows")
        if wf:
            if "project_id" not in wf:
                run("ALTER TABLE workflows ADD COLUMN project_id INTEGER")
            if "definition" not in wf:
                run("ALTER TABLE workflows ADD COLUMN definition JSON")
                if "graph_json" in wf:  # cố gắng giữ lại sơ đồ cũ
                    run("UPDATE workflows SET definition = graph_json::json "
                        "WHERE graph_json IS NOT NULL AND graph_json <> ''")
                run("""UPDATE workflows SET definition = '{"nodes": [], "edges": []}'::json
                       WHERE definition IS NULL""")
            if "is_active" not in wf:
                run("ALTER TABLE workflows ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
                if "enabled" in wf:
                    run("UPDATE workflows SET is_active = COALESCE(enabled, TRUE)")
            if wf.get("graph_json", ("", "YES"))[1] == "NO":
                run("ALTER TABLE workflows ALTER COLUMN graph_json DROP NOT NULL")
            # UNIQUE(name) chặn 2 project đặt trùng tên workflow
            for (cname,) in conn.execute(text(
                "SELECT conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                "WHERE t.relname = 'workflows' AND c.contype = 'u'"
            )).fetchall():
                run(f'ALTER TABLE workflows DROP CONSTRAINT "{cname}"')

        wr = columns("workflow_runs")
        if wr:
            if "node_status" not in wr:
                run("ALTER TABLE workflow_runs ADD COLUMN node_status JSON")
            log_type = wr.get("log", (None, None))[0]
            if log_type is not None and log_type not in ("json", "jsonb"):
                run("ALTER TABLE workflow_runs RENAME COLUMN log TO log_legacy")
                run("ALTER TABLE workflow_runs ADD COLUMN log JSON")
            elif "log" not in wr:
                run("ALTER TABLE workflow_runs ADD COLUMN log JSON")
            if wr.get("trigger_type", ("", "YES"))[1] == "NO":
                run("ALTER TABLE workflow_runs ALTER COLUMN trigger_type DROP NOT NULL")

        conn.commit()


try:
    _reconcile_workflow_tables()
except Exception as e:
    print(f"[migrate] workflow tables reconcile failed: {e}")

app = FastAPI(title="AI Team Dashboard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs.router,   prefix="/api/runs",   tags=["runs"])
app.include_router(tasks.router,  prefix="/api/tasks",  tags=["tasks"])
app.include_router(issues.router,   prefix="/api/issues",   tags=["issues"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(projects.router,  prefix="/api/projects", tags=["projects"])
app.include_router(agents.router,          prefix="/api/agents",         tags=["agents"])
app.include_router(project_tasks.router,  prefix="/api/project-tasks", tags=["project-tasks"])
app.include_router(system.router,          prefix="/api/system",       tags=["system"])
app.include_router(run_jobs.router,        prefix="/api/run-jobs",     tags=["run-jobs"])
app.include_router(workflows.router,       prefix="/api/workflows",    tags=["workflows"])
app.include_router(workflow_jobs.router,   prefix="/api/workflow-jobs", tags=["workflow-jobs"])
app.include_router(slack_events.router,    prefix="/api/slack",        tags=["slack"])


_POLL_INTERVAL_S = 5


async def _workflow_run_poll_loop():
    """Đọc lại trạng thái các task file 'running' mỗi 5s — CHỈ đọc file,
    không tự gọi Claude/opencode/git. Xem docstring routers/workflows.py."""
    while True:
        await asyncio.sleep(_POLL_INTERVAL_S)
        try:
            poll_running_workflow_runs()
        except Exception as e:
            print(f"[workflow-poll] error: {e}")


@app.on_event("startup")
async def _start_background_poller():
    asyncio.create_task(_workflow_run_poll_loop())


@app.get("/health")
def health():
    return {"status": "ok"}
