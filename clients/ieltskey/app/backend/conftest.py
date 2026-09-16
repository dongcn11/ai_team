"""Fixture dùng chung cho test.

File này nằm ở gốc backend/ nên pytest tự thêm backend/ vào sys.path —
nhờ vậy `from app.main import app` chạy được mà không cần cài package.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app


@pytest.fixture(name="session")
def session_fixture():
    """SQLite in-memory riêng cho từng test.

    StaticPool giữ đúng 1 connection — in-memory DB biến mất khi connection đóng.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    app.dependency_overrides[get_session] = lambda: session
    # Cố ý KHÔNG dùng `with TestClient(app)`: vào context sẽ chạy lifespan →
    # init_db() tạo file ieltskey.db thật ngay trong repo.
    yield TestClient(app)
    app.dependency_overrides.clear()
