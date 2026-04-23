from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List

from database import get_db
from models import Issue
from schemas import IssueCreate, IssueOut

router = APIRouter()


@router.post("/", response_model=IssueOut)
def create_issue(issue: IssueCreate, db: Session = Depends(get_db)):
    db_issue = Issue(
        run_id=issue.run_id,
        role=issue.role,
        severity=issue.severity,
        description=issue.description,
        suggestion=issue.suggestion,
    )
    db.add(db_issue)
    db.commit()
    db.refresh(db_issue)
    return db_issue


@router.get("/{run_id}", response_model=List[IssueOut])
def get_issues(run_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Issue)
        .filter(Issue.run_id == run_id)
        .order_by(desc(Issue.created_at))
        .all()
    )
