"""Kết nối SQLite qua SQLModel.

Đường dẫn DB lấy từ env `IELTSKEY_DB_URL` để test / docker đổi được mà không
phải sửa code. Mặc định là file `ieltskey.db` cạnh thư mục backend.
"""
import os
from pathlib import Path
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_URL = f"sqlite:///{BASE_DIR / 'ieltskey.db'}"
DB_URL = os.getenv("IELTSKEY_DB_URL", DEFAULT_DB_URL)

# check_same_thread=False: FastAPI chạy handler trên threadpool, mỗi request có
# thể rơi vào thread khác thread tạo connection.
engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})


def init_db() -> None:
    """Tạo bảng nếu chưa có. Gọi 1 lần lúc app khởi động."""
    # import để SQLModel.metadata biết các bảng trước khi create_all
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """Dependency: 1 session cho mỗi request, đóng khi request xong."""
    with Session(engine) as session:
        yield session
