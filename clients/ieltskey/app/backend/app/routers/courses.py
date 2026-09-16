"""API khóa học: tạo mới, xem danh sách, xem chi tiết."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..database import get_session
from ..models import Course, CourseLevel, CourseSkill, CourseStatus
from ..schemas import CourseCreate, CourseListResponse, CourseRead
from ..utils import slugify

router = APIRouter(prefix="/api/courses", tags=["courses"])

# Số hậu tố tối đa khi tự sinh slug ("...-2", "...-3", ...) trước khi chịu thua.
_MAX_SLUG_TRIES = 50


def _slug_taken(session: Session, slug: str) -> bool:
    return session.exec(select(Course.id).where(Course.slug == slug)).first() is not None


def _resolve_slug(session: Session, payload: CourseCreate) -> str:
    """Slug người dùng nhập thì phải độc nhất; slug tự sinh thì thêm hậu tố.

    Phân biệt hai đường này là có chủ đích: người dùng gõ tay slug là họ muốn
    đúng chuỗi đó (thường vì SEO / link đã phát ra ngoài), im lặng đổi thành
    "-2" sẽ hỏng link. Còn slug tự sinh thì họ không quan tâm, đổi được.
    """
    if payload.slug:
        if _slug_taken(session, payload.slug):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Slug '{payload.slug}' đã được dùng cho khóa học khác",
            )
        return payload.slug

    base = slugify(payload.title)
    candidate = base
    for i in range(2, _MAX_SLUG_TRIES + 2):
        if not _slug_taken(session, candidate):
            return candidate
        candidate = f"{base}-{i}"
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Quá nhiều khóa học trùng tên '{payload.title}', hãy nhập slug thủ công",
    )


@router.post("", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    session: Session = Depends(get_session),
) -> Course:
    """Tạo khóa học mới.

    409 nếu slug trùng, 422 nếu payload sai ràng buộc (xem `schemas.CourseCreate`).
    """
    course = Course(
        **payload.model_dump(exclude={"slug"}),
        slug=_resolve_slug(session, payload),
    )
    session.add(course)
    try:
        session.commit()
    except IntegrityError:
        # Hai request cùng slug chen nhau giữa lúc check và commit.
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Slug vừa bị khóa học khác chiếm mất, thử lại giúp",
        )
    session.refresh(course)
    return course


@router.get("", response_model=CourseListResponse)
def list_courses(
    session: Session = Depends(get_session),
    q: Optional[str] = Query(default=None, description="Tìm theo tên khóa học"),
    course_status: Optional[CourseStatus] = Query(default=None, alias="status"),
    level: Optional[CourseLevel] = None,
    skill: Optional[CourseSkill] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> CourseListResponse:
    """Danh sách khóa học, mới nhất trước."""
    filters = []
    if q:
        # autoescape: người dùng gõ '%' hay '_' phải là ký tự thường, không phải wildcard
        filters.append(func.lower(Course.title).contains(q.strip().lower(), autoescape=True))
    if course_status is not None:
        filters.append(Course.status == course_status)
    if level is not None:
        filters.append(Course.level == level)
    if skill is not None:
        filters.append(Course.skill == skill)

    total = session.exec(
        select(func.count()).select_from(Course).where(*filters)
    ).one()

    rows = session.exec(
        select(Course).where(*filters).order_by(Course.id.desc()).offset(offset).limit(limit)
    ).all()

    return CourseListResponse(
        items=[CourseRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{course_id}", response_model=CourseRead)
def get_course(course_id: int, session: Session = Depends(get_session)) -> Course:
    course = session.get(Course, course_id)
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy khóa học #{course_id}",
        )
    return course
