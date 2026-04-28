import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from database import get_db
from main import app
from models.user import User
from utils.security import hash_password


@pytest.fixture(name="session")
def session_fixture():
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
    def get_session_override():
        return session

    app.dependency_overrides[get_db] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_register_success(client):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "Password123"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert "password" not in data
    assert "password_hash" not in data


def test_register_duplicate_username(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "Password123"
        }
    )
    response = client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "other@example.com",
            "password": "Password123"
        }
    )
    assert response.status_code == 409
    assert "Username already exists" in response.json()["detail"]


def test_register_duplicate_email(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "Password123"
        }
    )
    response = client.post(
        "/api/auth/register",
        json={
            "username": "otheruser",
            "email": "test@example.com",
            "password": "Password123"
        }
    )
    assert response.status_code == 409
    assert "Email already registered" in response.json()["detail"]


def test_register_weak_password(client):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "weak"
        }
    )
    assert response.status_code in [400, 422]


def test_register_invalid_email(client):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "not-an-email",
            "password": "Password123"
        }
    )
    assert response.status_code == 400


def test_login_success(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "Password123"
        }
    )
    response = client.post(
        "/api/auth/login",
        json={
            "email": "test@example.com",
            "password": "Password123"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 1800


def test_login_invalid_credentials(client):
    response = client.post(
        "/api/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "WrongPassword1"
        }
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


def test_login_wrong_password(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "Password123"
        }
    )
    response = client.post(
        "/api/auth/login",
        json={
            "email": "test@example.com",
            "password": "WrongPassword1"
        }
    )
    assert response.status_code == 401


def test_token_refresh(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "Password123"
        }
    )
    login_response = client.post(
        "/api/auth/login",
        json={
            "email": "test@example.com",
            "password": "Password123"
        }
    )
    refresh_token = login_response.json()["refresh_token"]

    response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_token_refresh_invalid(client):
    response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": "invalid-token"}
    )
    assert response.status_code == 401


def test_logout(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "Password123"
        }
    )
    login_response = client.post(
        "/api/auth/login",
        json={
            "email": "test@example.com",
            "password": "Password123"
        }
    )
    access_token = login_response.json()["access_token"]

    response = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert "Successfully logged out" in response.json()["message"]


def test_logout_without_token(client):
    response = client.post("/api/auth/logout")
    assert response.status_code == 401
