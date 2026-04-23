from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from routers import runs, tasks, issues

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
app.include_router(issues.router, prefix="/api/issues", tags=["issues"])


@app.get("/health")
def health():
    return {"status": "ok"}
