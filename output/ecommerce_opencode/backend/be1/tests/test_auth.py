import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine, Session
from unittest.mock import patch

from main import app
from database import get_db

DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(DATABASE_URL)


def override_get_db():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


class TestRegistration:
    def test_register_success(self):
        response = client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "Test1234!",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"
        assert "id" in data
        assert "password" not in data

    def test_register_duplicate_username(self):
        client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "Test1234!",
            },
        )
        response = client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "other@example.com",
                "password": "Test1234!",
            },
        )
        assert response.status_code == 409

    def test_register_duplicate_email(self):
        client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "Test1234!",
            },
        )
        response = client.post(
            "/api/auth/register",
            json={
                "username": "otheruser",
                "email": "test@example.com",
                "password": "Test1234!",
            },
        )
        assert response.status_code == 409

    def test_register_invalid_username(self):
        response = client.post(
            "/api/auth/register",
            json={
                "username": "test user!",
                "email": "test@example.com",
                "password": "Test1234!",
            },
        )
        assert response.status_code == 422

    def test_register_weak_password(self):
        response = client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "weak",
            },
        )
        assert response.status_code == 422

    def test_register_invalid_email(self):
        response = client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "not-an-email",
                "password": "Test1234!",
            },
        )
        assert response.status_code == 422


class TestLogin:
    def test_login_success(self):
        client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "Test1234!",
            },
        )
        response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "Test1234!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_invalid_credentials(self):
        client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "Test1234!",
            },
        )
        response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "wrongpassword"},
        )
        assert response.status_code == 401


class TestLogout:
    def test_logout_success(self):
        client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "Test1234!",
            },
        )
        login_response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "Test1234!"},
        )
        token = login_response.json()["access_token"]
        response = client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    def test_logout_without_token(self):
        response = client.post("/api/auth/logout")
        assert response.status_code == 403


class TestTokenRefresh:
    def test_refresh_token_success(self):
        client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "Test1234!",
            },
        )
        login_response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "Test1234!"},
        )
        refresh_token = login_response.json()["refresh_token"]
        response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_refresh_invalid_token(self):
        response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": "invalid-token"},
        )
        assert response.status_code == 401


class TestPasswordHashing:
    def test_password_hash_and_verify(self):
        from app.utils.security import get_password_hash, verify_password

        password = "Test1234!"
        hashed = get_password_hash(password)
        assert hashed != password
        assert verify_password(password, hashed)
        assert not verify_password("wrongpassword", hashed)


class TestTokenGeneration:
    def test_access_token_creation(self):
        from app.utils.token import create_access_token, decode_access_token

        token = create_access_token(data={"sub": "test-user-id"})
        payload = decode_access_token(token)
        assert payload["sub"] == "test-user-id"

    def test_refresh_token_creation(self):
        from app.utils.token import create_refresh_token, decode_access_token

        token = create_refresh_token(data={"sub": "test-user-id"})
        payload = decode_access_token(token)
        assert payload["sub"] == "test-user-id"
