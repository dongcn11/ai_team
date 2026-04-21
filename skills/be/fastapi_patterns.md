# Skill: FastAPI Patterns

## Cấu trúc file chuẩn
```
backend/
├── main.py           ← app init, middleware, include routers
├── database.py       ← engine, get_db dependency
├── models.py         ← SQLModel table classes
├── schemas.py        ← Pydantic request/response schemas
├── auth.py           ← JWT logic, get_current_user dependency
└── routes/
    ├── auth.py       ← /auth/register, /auth/login
    └── tasks.py      ← /tasks CRUD
```

## App setup chuẩn
```python
# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import create_db_and_tables
from routes import auth, tasks

app = FastAPI(title="API", version="1.0.0")

app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

app.include_router(auth.router,  prefix="/api/auth",  tags=["auth"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
```

## Router pattern
```python
# routes/tasks.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from database import get_db
from models import Task
from schemas import TaskCreate, TaskUpdate, TaskResponse
from auth import get_current_user

router = APIRouter()

@router.get("/", response_model=list[TaskResponse])
def list_tasks(
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    query = select(Task).where(Task.user_id == current_user.id)
    if status:
        query = query.where(Task.status == status)
    return db.exec(query).all()
```

## Dependency injection
```python
# database.py
from sqlmodel import SQLModel, create_engine, Session

engine = create_engine("sqlite:///./app.db")

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_db():
    with Session(engine) as session:
        yield session
```

## Response format nhất quán
```python
# Luôn dùng response_model để filter fields
@router.post("/", response_model=TaskResponse, status_code=201)
def create_task(task_in: TaskCreate, ...):
    ...
```
