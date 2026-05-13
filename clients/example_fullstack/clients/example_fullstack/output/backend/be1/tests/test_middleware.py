from datetime import datetime, timedelta, timezone
from jose import jwt
from app.config import settings


def test_missing_auth_header(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_invalid_token(client):
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalidtoken123"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_TOKEN"


def test_expired_token(client, session):
    from app.models.user import User
    from app.security import hash_password
    user = User(email="expired@example.com", password_hash=hash_password("TestPass123"))
    session.add(user)
    session.commit()
    session.refresh(user)

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
        "jti": "expired_jti_123",
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_valid_token_returns_user(client, auth_headers):
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert "created_at" in data


def test_deleted_user_token_fails(client, auth_headers, session):
    from app.models.user import User
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    user_data = response.json()
    user = session.get(User, user_data["id"])
    session.delete(user)
    session.commit()

    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 401
