from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from routers import runs, tasks, issues, settings, projects, agents, project_tasks, system

Base.metadata.create_all(bind=engine)

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
