"""Schema request/response + toàn bộ ràng buộc nghiệp vụ của khóa học."""
import re
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import CourseLevel, CourseSkill, CourseStatus

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Trần giá 1 tỷ VNĐ — chặn lỗi gõ thừa số 0 chứ không phải giới hạn kinh doanh.
MAX_PRICE_VND = 1_000_000_000


class CourseCreate(BaseModel):
    """Payload tạo khóa học. `slug` bỏ trống thì backend tự sinh từ `title`."""

    title: str = Field(min_length=3, max_length=160)
    slug: Optional[str] = Field(default=None, max_length=180)
    description: Optional[str] = Field(default=None, max_length=4000)

    level: CourseLevel
    skill: CourseSkill = CourseSkill.full
    target_band: Optional[float] = Field(default=None, ge=4.0, le=9.0)

    duration_weeks: int = Field(ge=1, le=104)
    sessions_per_week: int = Field(ge=1, le=14)
    price_vnd: int = Field(ge=0, le=MAX_PRICE_VND)
    max_students: int = Field(ge=1, le=500)

    start_date: Optional[date] = None
    status: CourseStatus = CourseStatus.draft

    @field_validator("title")
    @classmethod
    def _clean_title(cls, v: str) -> str:
        v = " ".join(v.split())          # gộp khoảng trắng thừa, bỏ đầu/cuối
        if len(v) < 3:
            raise ValueError("Tên khóa học phải có ít nhất 3 ký tự")
        return v

    @field_validator("description")
    @classmethod
    def _clean_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        if not v:
            return None
        if not SLUG_RE.match(v):
            raise ValueError(
                "Slug chỉ gồm chữ thường, số và dấu gạch ngang (vd: ielts-6-5-cap-toc)"
            )
        if len(v) < 3:
            raise ValueError("Slug phải có ít nhất 3 ký tự")
        return v

    @field_validator("target_band")
    @classmethod
    def _check_band(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        # IELTS chỉ chấm theo bước 0.5
        if round(v * 2) != v * 2:
            raise ValueError("Band mục tiêu phải là bội của 0.5 (vd: 6.5)")
        return float(v)

    @model_validator(mode="after")
    def _check_publishable(self) -> "CourseCreate":
        """Mở đăng ký ngay thì phải đủ thông tin học viên cần để quyết định."""
        if self.status is CourseStatus.published:
            if self.start_date is None:
                raise ValueError(
                    "Khóa học mở đăng ký (published) phải có ngày khai giảng"
                )
            if self.price_vnd <= 0:
                raise ValueError(
                    "Khóa học mở đăng ký (published) phải có học phí lớn hơn 0"
                )
        return self


class CourseRead(BaseModel):
    """Dữ liệu trả về cho client."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    description: Optional[str]

    level: CourseLevel
    skill: CourseSkill
    target_band: Optional[float]

    duration_weeks: int
    sessions_per_week: int
    total_sessions: int
    price_vnd: int
    max_students: int

    start_date: Optional[date]
    status: CourseStatus

    created_at: datetime
    updated_at: datetime


class CourseListResponse(BaseModel):
    items: list[CourseRead]
    total: int
    limit: int
    offset: int
