"""Bảng dữ liệu (SQLModel table models).

Lưu ý: SQLModel KHÔNG chạy validation trên class có `table=True` — mọi ràng buộc
nghiệp vụ nằm ở `schemas.py`, model ở đây chỉ mô tả cột.
"""
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Giờ UTC không kèm tzinfo — SQLite không lưu offset, để naive cho nhất quán."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CourseLevel(str, Enum):
    """Trình độ đầu vào của lớp.

    Tên member trùng giá trị vì SQLAlchemy lưu Enum theo `.name`.
    """

    foundation = "foundation"      # mất gốc, chưa thi bao giờ
    pre_ielts = "pre_ielts"        # đã có nền tảng, làm quen format
    band_5_5 = "band_5_5"
    band_6_5 = "band_6_5"
    band_7_plus = "band_7_plus"


class CourseSkill(str, Enum):
    """Kỹ năng lớp tập trung vào."""

    full = "full"                  # cả 4 kỹ năng
    listening = "listening"
    reading = "reading"
    writing = "writing"
    speaking = "speaking"


class CourseStatus(str, Enum):
    draft = "draft"                # đang soạn, chưa hiện ra ngoài
    published = "published"        # đang mở đăng ký
    archived = "archived"          # đã đóng


class Course(SQLModel, table=True):
    __tablename__ = "courses"

    id: Optional[int] = Field(default=None, primary_key=True)

    title: str = Field(index=True)
    slug: str = Field(index=True, unique=True)
    description: Optional[str] = Field(default=None)

    level: CourseLevel = Field(default=CourseLevel.foundation)
    skill: CourseSkill = Field(default=CourseSkill.full)
    target_band: Optional[float] = Field(default=None)   # band đầu ra cam kết

    duration_weeks: int = Field(default=8)
    sessions_per_week: int = Field(default=2)
    price_vnd: int = Field(default=0)
    max_students: int = Field(default=20)

    start_date: Optional[date] = Field(default=None)
    status: CourseStatus = Field(default=CourseStatus.draft, index=True)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def total_sessions(self) -> int:
        return self.duration_weeks * self.sessions_per_week
