def test_register_success(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "newuser@example.com", "password": "SecurePass1"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert "id" in data
    assert "created_at" in data
    assert "password_hash" not in data


def test_register_duplicate_email(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "password": "SecurePass1"},
    )
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "password": "SecurePass2"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EMAIL_EXISTS"


def test_register_weak_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_register_password_no_digit(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "nodigit@example.com", "password": "NoDigitsHere"},
    )
    assert response.status_code == 422


def test_register_invalid_email(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "SecurePass1"},
    )
    assert response.status_code == 422


def test_register_email_normalized(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "  UPPER@Example.COM  ", "password": "SecurePass1"},
    )
    assert response.status_code == 201
    assert response.json()["email"] == "upper@example.com"
