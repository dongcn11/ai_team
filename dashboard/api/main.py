from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import engine, Base
from routers import runs, tasks, issues, settings, projects, agents, project_tasks, system

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


try:
    _ensure_column("project_tasks", "acceptance_criteria", "TEXT")
except Exception as e:  # best-effort; log so failures are visible in container logs
    print(f"[migrate] acceptance_criteria column ensure failed: {e}")

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


@app.get("/health")
def health():
    return {"status": "ok"}
