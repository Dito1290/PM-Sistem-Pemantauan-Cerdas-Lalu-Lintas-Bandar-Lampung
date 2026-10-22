"""Login, token validation, logout and role checks (ST-01, ST-02)."""
from __future__ import annotations

from citysight.extensions import db
from citysight.models import User

from .conftest import ADMIN_PASSWORD, OPERATOR_PASSWORD


def login(client, username, password, **kwargs):
    return client.post("/api/auth/login", json={"username": username, "password": password}, **kwargs)


def test_login_success_returns_token_and_role(client, users):
    res = login(client, "admin", ADMIN_PASSWORD)
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["token_type"] == "Bearer"
    assert data["access_token"]
    assert data["expires_in"] == 3600
    assert data["user"]["role"] == "admin"
    assert "password_hash" not in data["user"]
    assert "password" not in res.get_data(as_text=True)


def test_login_accepts_email_case_insensitive(client, users):
    res = login(client, "OPERATOR@example.test", OPERATOR_PASSWORD)
    assert res.status_code == 200
    assert res.get_json()["data"]["user"]["role"] == "operator"


def test_login_wrong_password(client, users):
    res = login(client, "admin", "wrong-password-1")
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "invalid_credentials"


def test_login_unknown_user_same_error(client, users):
    res = login(client, "nobody", "whatever-123")
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "invalid_credentials"


def test_login_validation(client):
    assert client.post("/api/auth/login", json={"username": "admin"}).status_code == 422
    assert client.post("/api/auth/login", data="x", content_type="text/plain").status_code == 415
    res = client.post("/api/auth/login", json={"username": "a", "password": "b", "role": "admin"})
    assert res.status_code == 422  # unknown fields are rejected


def test_login_rate_limited_after_repeated_failures(client, users):
    for _ in range(5):
        assert login(client, "admin", "bad-pass-1").status_code == 401
    res = login(client, "admin", ADMIN_PASSWORD)
    assert res.status_code == 429
    assert int(res.headers["Retry-After"]) > 0


def test_private_endpoint_without_token(client):
    for method, path in [("get", "/api/cameras"), ("get", "/api/stats/summary"),
                         ("get", "/api/cameras/1/detections"), ("post", "/api/auth/logout")]:
        res = getattr(client, method)(path)
        assert res.status_code == 401, path
        assert res.get_json()["error"]["code"] == "missing_token"


def test_invalid_token(client):
    res = client.get("/api/cameras", headers={"Authorization": "Bearer not.a.jwt"})
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "invalid_token"


def test_tampered_token_rejected(client, tokens):
    header, payload, signature = tokens["operator"].split(".")
    forged = f"{header}.{payload}.{signature[:-4]}AAAA"
    res = client.get("/api/cameras", headers={"Authorization": f"Bearer {forged}"})
    assert res.status_code == 401


def test_expired_token(client, expired_token):
    res = client.get("/api/cameras", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "token_expired"


def test_query_string_token_not_accepted_on_rest_endpoints(client, tokens):
    res = client.get(f"/api/cameras?access_token={tokens['admin']}")
    assert res.status_code == 401


def test_logout_revokes_token(client, users):
    token = login(client, "operator", OPERATOR_PASSWORD).get_json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "token_revoked"


def test_role_is_read_from_database_not_token(app, client, users, admin_headers):
    # Demote the admin after the token was issued: admin actions must now fail.
    with app.app_context():
        db.session.get(User, users["admin"]).role = "operator"
        db.session.commit()
    res = client.post("/api/cameras", headers=admin_headers, json={
        "name": "X", "location": "Y", "stream_url": "rtsp://cctv.example.test/x"})
    assert res.status_code == 403


def test_token_of_deleted_user_rejected(app, client, users, operator_headers):
    with app.app_context():
        db.session.delete(db.session.get(User, users["operator"]))
        db.session.commit()
    assert client.get("/api/cameras", headers=operator_headers).status_code == 401


def test_me_returns_profile_without_hash(client, operator_headers):
    data = client.get("/api/auth/me", headers=operator_headers).get_json()["data"]
    assert data["username"] == "operator"
    assert set(data) == {"id", "username", "email", "role", "created_at"}
