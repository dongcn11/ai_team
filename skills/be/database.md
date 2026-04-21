# Skill: Database (SQLModel)

## Model definition chuẩn
```python
from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional
import uuid

class Task(SQLModel, table=True):
    id:          str      = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    title:       str      = Field(index=True)
    description: str      = Field(default="")
    status:      str      = Field(default="todo")       # todo | in-progress | done
    priority:    str      = Field(default="medium")     # low | medium | high
    deadline:    Optional[datetime] = None
    user_id:     str      = Field(foreign_key="user.id", index=True)
    created_at:  datetime = Field(default_factory=datetime.utcnow)
    updated_at:  datetime = Field(default_factory=datetime.utcnow)
```

## Schema tách biệt với Model
```python
# schemas.py — không expose toàn bộ model ra ngoài
class TaskCreate(SQLModel):
    title:       str
    description: str = ""
    priority:    str = "medium"
    deadline:    Optional[datetime] = None

class TaskResponse(SQLModel):
    id:          str
    title:       str
    description: str
    status:      str
    priority:    str
    deadline:    Optional[datetime]
    created_at:  datetime
    # Không có user_id — không expose
```

## Query patterns
```python
from sqlmodel import select

# List với filter
tasks = db.exec(
    select(Task)
    .where(Task.user_id == user_id)
    .where(Task.status == status)
    .order_by(Task.created_at.desc())
).all()

# Get one hoặc 404
task = db.get(Task, task_id)
if not task:
    raise HTTPException(404, "Không tìm thấy")

# Update
task.title      = update_data.title
task.updated_at = datetime.utcnow()
db.add(task)
db.commit()
db.refresh(task)

# Delete
db.delete(task)
db.commit()
```
