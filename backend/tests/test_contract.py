"""Response envelope, error safety, CORS and SSE contract (docs/API_CONTRACT.md)."""
from __future__ import annotations

import json
import threading
import time

import pytest
from sqlalchemy.exc import OperationalError

from citysight.services.realtime import CHANNEL


def test_success_envelope(client, operator_headers, make_camera):
    make_camera()
    for path in ["/api/cameras", "/api/cameras/1", "/api/cameras/1/detections",
                 "/api/cameras/1/stats/hourly", "/api/cameras/1/stats/daily", "/api/stats/summary",
                 "/api/auth/me"]:
        res = client.get(path, headers=operator_headers)
        assert res.status_code == 200, path
        assert res.is_json and "data" in res.get_json(), path
        assert res.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("method, path, status", [
    ("get", "/api/nope", 404),
    ("patch", "/api/cameras/1", 405),
])
def test_http_errors_are_json(client, admin_headers, method, path, status):
    res = getattr(client, method)(path, headers=admin_headers)
    assert res.status_code == status
    body = res.get_json()
    assert set(body["error"]) >= {"code", "message"}


def test_unhandled_error_hides_internals(app):
    from citysight import create_app

    app = create_app("testing")  # fresh instance so test routes can still be added

    @app.get("/api/_test/boom")
    def _boom():
        raise RuntimeError("secret internal detail /etc/passwd")

    @app.get("/api/_test/db-down")
    def _db_down():
        raise OperationalError("SELECT 1", {}, Exception("password=hunter2 host=10.0.0.1"))

    client = app.test_client()
    res = client.get("/api/_test/boom")
    assert res.status_code == 500
    assert res.get_json() == {"error": {"code": "internal_error", "message": "Terjadi kesalahan pada server."}}
    assert "secret" not in res.get_data(as_text=True)

    res = client.get("/api/_test/db-down")
    assert res.status_code == 503
    assert "hunter2" not in res.get_data(as_text=True)
    assert res.get_json()["error"]["code"] == "database_unavailable"


def test_security_headers_and_request_id(client):
    res = client.get("/api/health", headers={"X-Request-ID": "abc123"})
    assert res.headers["X-Request-ID"] == "abc123"
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


def test_cors_allows_configured_origin_only(client):
    ok = client.options("/api/cameras", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization, Content-Type"})
    assert ok.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    assert "Authorization" in ok.headers.get("Access-Control-Allow-Headers", "")
    evil = client.options("/api/cameras", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "Access-Control-Allow-Origin" not in evil.headers


def test_oversized_body_rejected(client, admin_headers):
    res = client.post("/api/cameras", headers=admin_headers,
                      data=json.dumps({"name": "x" * 70_000}), content_type="application/json")
    assert res.status_code == 413
    assert res.get_json()["error"]["code"] == "payload_too_large"


# --- SSE ------------------------------------------------------------------------

def _collect_sse(client, url, headers=None):
    res = client.get(url, headers=headers or {}, buffered=False)
    return res, (b"".join(res.response).decode() if res.status_code == 200 else None)


def test_sse_requires_auth(client):
    assert client.get("/api/stream/detections").status_code == 401


def test_sse_streams_filtered_events(app, client, redis_client, tokens, make_camera):
    a, b = make_camera(name="A"), make_camera(name="B")

    def publish():
        time.sleep(0.8)
        redis_client.publish(CHANNEL, json.dumps({"camera_id": b, "timestamp": "t1", "total_vehicle": 1}))
        redis_client.publish(CHANNEL, json.dumps({"camera_id": a, "timestamp": "t2", "total_vehicle": 4}))

    threading.Thread(target=publish).start()
    res, body = _collect_sse(client, f"/api/stream/detections?camera_id={a}&access_token={tokens['operator']}")
    assert res.status_code == 200
    assert res.mimetype == "text/event-stream"
    assert "event: ready" in body
    events = [json.loads(line[6:]) for line in body.splitlines()
              if line.startswith("data: ") and "camera_id\": " in line and "timestamp" in line]
    assert events == [{"camera_id": a, "timestamp": "t2", "total_vehicle": 4}]
    assert f"id: {a}-t2" in body


def test_sse_unknown_camera(client, tokens):
    res = client.get(f"/api/stream/detections?camera_id=42&access_token={tokens['admin']}")
    assert res.status_code == 404
    res = client.get(f"/api/stream/detections?camera_id=x&access_token={tokens['admin']}")
    assert res.status_code == 422
