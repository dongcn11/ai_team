def test_logout_success(client, auth_headers):
    response = client.post("/api/v1/auth/logout", headers=auth_headers)
    assert response.status_code == 204


def test_token_revoked_after_logout(client, auth_headers):
    client.post("/api/v1/auth/logout", headers=auth_headers)
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "TOKEN_REVOKED"


def test_double_logout(client, auth_headers):
    client.post("/api/v1/auth/logout", headers=auth_headers)
    response = client.post("/api/v1/auth/logout", headers=auth_headers)
    assert response.status_code == 401
