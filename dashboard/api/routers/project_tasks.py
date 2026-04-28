from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List
from datetime import datetime

from database import get_db
from models import Project, ProjectTask, TaskDocument, TaskComment, SubTask
from schemas import (
    ProjectTaskCreate, ProjectTaskUpdate, ProjectTaskOut,
    TaskDocCreate, TaskDocOut,
    TaskCommentCreate, TaskCommentOut,
    SubTaskCreate, SubTaskUpdate, SubTaskOut,
)

router = APIRouter()


# ── Tasks ──

@router.get("/{project_id}", response_model=List[ProjectTaskOut])
def list_tasks(project_id: int, status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(ProjectTask).filter(ProjectTask.project_id == project_id).order_by(desc(ProjectTask.created_at))
    if status:
        q = q.filter(ProjectTask.status == status)
    return q.all()


@router.post("/{project_id}", response_model=ProjectTaskOut)
def create_task(project_id: int, payload: ProjectTaskCreate, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    task = ProjectTask(
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        priority=payload.priority,
        assigned_agent_id=payload.assigned_agent_id,
        due_at=payload.due_at,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("/{project_id}/{task_id}", response_model=ProjectTaskOut)
def get_task(project_id: int, task_id: int, db: Session = Depends(get_db)):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id, ProjectTask.project_id == project_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{project_id}/{task_id}", response_model=ProjectTaskOut)
def update_task(project_id: int, task_id: int, payload: ProjectTaskUpdate, db: Session = Depends(get_db)):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id, ProjectTask.project_id == project_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if payload.name is not None:
        task.name = payload.name
    if payload.description is not None:
        task.description = payload.description
    if payload.status is not None:
        task.status = payload.status
        if payload.status == "done" and not task.completed_at:
            task.completed_at = datetime.utcnow()
            task.progress = 100
    if payload.priority is not None:
        task.priority = payload.priority
    if payload.progress is not None:
        task.progress = max(0, min(100, payload.progress))
    if payload.assigned_agent_id is not None:
        task.assigned_agent_id = payload.assigned_agent_id
    if payload.due_at is not None:
        task.due_at = payload.due_at

    db.commit()
    db.refresh(task)
    return task


@router.delete("/{project_id}/{task_id}")
def delete_task(project_id: int, task_id: int, db: Session = Depends(get_db)):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id, ProjectTask.project_id == project_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"ok": True}


# ── Task Documents ──

@router.get("/{project_id}/{task_id}/docs", response_model=List[TaskDocOut])
def list_docs(project_id: int, task_id: int, db: Session = Depends(get_db)):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id, ProjectTask.project_id == project_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return db.query(TaskDocument).filter(TaskDocument.task_id == task_id).order_by(desc(TaskDocument.created_at)).all()


@router.post("/{project_id}/{task_id}/docs", response_model=TaskDocOut)
def create_doc(project_id: int, task_id: int, payload: TaskDocCreate, db: Session = Depends(get_db)):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id, ProjectTask.project_id == project_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    doc = TaskDocument(task_id=task_id, title=payload.title, content=payload.content, doc_type=payload.doc_type)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.put("/{project_id}/{task_id}/docs/{doc_id}", response_model=TaskDocOut)
def update_doc(project_id: int, task_id: int, doc_id: int, payload: TaskDocCreate, db: Session = Depends(get_db)):
    doc = db.query(TaskDocument).filter(TaskDocument.id == doc_id, TaskDocument.task_id == task_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if payload.title is not None:
        doc.title = payload.title
    if payload.content is not None:
        doc.content = payload.content
    if payload.doc_type is not None:
        doc.doc_type = payload.doc_type

    db.commit()
    db.refresh(doc)
    return doc


@router.delete("/{project_id}/{task_id}/docs/{doc_id}")
def delete_doc(project_id: int, task_id: int, doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(TaskDocument).filter(TaskDocument.id == doc_id, TaskDocument.task_id == task_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()
    return {"ok": True}


# ── Task Comments ──

@router.get("/{project_id}/{task_id}/comments", response_model=List[TaskCommentOut])
def list_comments(project_id: int, task_id: int, db: Session = Depends(get_db)):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id, ProjectTask.project_id == project_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return db.query(TaskComment).filter(TaskComment.task_id == task_id).order_by(TaskComment.created_at).all()


@router.post("/{project_id}/{task_id}/comments", response_model=TaskCommentOut)
def create_comment(project_id: int, task_id: int, payload: TaskCommentCreate, db: Session = Depends(get_db)):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id, ProjectTask.project_id == project_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    comment = TaskComment(task_id=task_id, author=payload.author, content=payload.content)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@router.delete("/{project_id}/{task_id}/comments/{comment_id}")
def delete_comment(project_id: int, task_id: int, comment_id: int, db: Session = Depends(get_db)):
    comment = db.query(TaskComment).filter(TaskComment.id == comment_id, TaskComment.task_id == task_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    db.delete(comment)
    db.commit()
    return {"ok": True}


# ── SubTasks ──

@router.get("/{project_id}/{task_id}/subtasks", response_model=List[SubTaskOut])
def list_subtasks(project_id: int, task_id: int, db: Session = Depends(get_db)):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id, ProjectTask.project_id == project_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return db.query(SubTask).filter(SubTask.task_id == task_id).order_by(SubTask.created_at).all()


@router.post("/{project_id}/{task_id}/subtasks", response_model=SubTaskOut)
def create_subtask(project_id: int, task_id: int, payload: SubTaskCreate, db: Session = Depends(get_db)):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id, ProjectTask.project_id == project_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    sub = SubTask(task_id=task_id, name=payload.name, assigned_agent_id=payload.assigned_agent_id)
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.put("/{project_id}/{task_id}/subtasks/{sub_id}", response_model=SubTaskOut)
def update_subtask(project_id: int, task_id: int, sub_id: int, payload: SubTaskUpdate, db: Session = Depends(get_db)):
    sub = db.query(SubTask).filter(SubTask.id == sub_id, SubTask.task_id == task_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="SubTask not found")

    if payload.name is not None:
        sub.name = payload.name
    if payload.status is not None:
        sub.status = payload.status
    if payload.assigned_agent_id is not None:
        sub.assigned_agent_id = payload.assigned_agent_id

    db.commit()
    db.refresh(sub)
    return sub


@router.delete("/{project_id}/{task_id}/subtasks/{sub_id}")
def delete_subtask(project_id: int, task_id: int, sub_id: int, db: Session = Depends(get_db)):
    sub = db.query(SubTask).filter(SubTask.id == sub_id, SubTask.task_id == task_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="SubTask not found")
    db.delete(sub)
    db.commit()
    return {"ok": True}
