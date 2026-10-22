"""Camera management (FT-08, UC-04) and role enforcement."""
from __future__ import annotations

import pytest

from citysight.extensions import db
from citysight.models import Camera

VALID = {
    "name": "Simpang Tugu Adipura",
    "location": "Jl. Teuku Umar, Bandar Lampung",
    "latitude": -5.4180,
    "longitude": 105.2620,
    "stream_url": "rtsp://cctv.example.test/live/1",
}


def test_admin_creates_camera(client, admin_headers):
    res = client.post("/api/cameras", headers=admin_headers, json=VALID)
    assert res.status_code == 201
    data = res.get_json()["data"]
    assert data["id"] > 0
    assert data["name"] == VALID["name"]
    assert data["status"] == "active"
    assert data["latitude"] == pytest.approx(-5.418)
    assert data["stream_url"] == VALID["stream_url"]


def test_operator_cannot_create_update_delete(client, operator_headers, make_camera):
    camera_id = make_camera()
    assert client.post("/api/cameras", headers=operator_headers, json=VALID).status_code == 403
    assert client.put(f"/api/cameras/{camera_id}", headers=operator_headers,
                      json={"name": "Hack"}).status_code == 403
    assert client.delete(f"/api/cameras/{camera_id}", headers=operator_headers).status_code == 403
    res = client.delete(f"/api/cameras/{camera_id}", headers=operator_headers)
    assert res.get_json()["error"]["code"] == "forbidden"


def test_operator_can_list_but_not_see_stream_url(client, operator_headers, admin_headers, make_camera):
    make_camera(url="rtsp://user:secret@cctv.example.test/live")
    op = client.get("/api/cameras", headers=operator_headers).get_json()
    assert op["meta"]["count"] == 1
    assert "stream_url" not in op["data"][0]
    assert "secret" not in str(op)
    adm = client.get("/api/cameras", headers=admin_headers).get_json()
    assert adm["data"][0]["stream_url"].startswith("rtsp://")


def test_list_includes_runtime_stream_state(client, operator_headers, make_camera):
    make_camera()
    camera = client.get("/api/cameras", headers=operator_headers).get_json()["data"][0]
    assert camera["stream"]["state"] == "offline"  # ingest service not running


def test_update_camera_partial(client, admin_headers, make_camera):
    camera_id = make_camera()
    res = client.put(f"/api/cameras/{camera_id}", headers=admin_headers,
                     json={"location": "Jl. Raden Intan", "status": "inactive"})
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["location"] == "Jl. Raden Intan"
    assert data["status"] == "inactive"
    assert data["name"] == "Simpang Tugu Adipura"


def test_delete_is_soft_and_keeps_history(app, client, admin_headers, make_camera):
    camera_id = make_camera()
    assert client.delete(f"/api/cameras/{camera_id}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/cameras/{camera_id}", headers=admin_headers).status_code == 404
    assert client.get("/api/cameras", headers=admin_headers).get_json()["data"] == []
    with app.app_context():
        row = db.session.get(Camera, camera_id)
        assert row is not None and row.deleted_at is not None and row.status == "inactive"
    # Name can be reused after deletion.
    assert client.post("/api/cameras", headers=admin_headers,
                       json={**VALID, "name": "Simpang Tugu Adipura"}).status_code == 201
    # Deleting twice -> 404
    assert client.delete(f"/api/cameras/{camera_id}", headers=admin_headers).status_code == 404


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_camera_not_found(client, admin_headers, method):
    kwargs = {"json": {"name": "x"}} if method == "put" else {}
    res = getattr(client, method)("/api/cameras/9999", headers=admin_headers, **kwargs)
    assert res.status_code == 404
    assert res.get_json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("payload, field", [
    ({**VALID, "name": ""}, "name"),
    ({**VALID, "latitude": 91}, "latitude"),
    ({**VALID, "longitude": -181}, "longitude"),
    ({k: v for k, v in VALID.items() if k != "stream_url"}, "stream_url"),
    ({**VALID, "status": "broken"}, "status"),
    ({**VALID, "extra": 1}, "extra"),
])
def test_create_validation_errors(client, admin_headers, payload, field):
    res = client.post("/api/cameras", headers=admin_headers, json=payload)
    assert res.status_code == 422
    body = res.get_json()["error"]
    assert body["code"] == "validation_error"
    assert any(field in (d["field"] or "") for d in body["details"]), body


def test_latitude_without_longitude_rejected(client, admin_headers):
    payload = {k: v for k, v in VALID.items() if k != "longitude"}
    assert client.post("/api/cameras", headers=admin_headers, json=payload).status_code == 422


@pytest.mark.parametrize("url", [
    "ftp://cctv.example.test/x", "javascript:alert(1)", "rtsp://", "not a url", "/etc/passwd",
])
def test_stream_url_rejected(app, client, admin_headers, url):
    app.config["ALLOW_FILE_SOURCES"] = False
    try:
        res = client.post("/api/cameras", headers=admin_headers, json={**VALID, "stream_url": url})
    finally:
        app.config["ALLOW_FILE_SOURCES"] = True
    assert res.status_code == 422


def test_stream_host_allowlist(app, client, admin_headers):
    app.config["STREAM_ALLOWED_HOSTS"] = ["cctv.allowed.test"]
    try:
        bad = client.post("/api/cameras", headers=admin_headers, json=VALID)
        good = client.post("/api/cameras", headers=admin_headers,
                           json={**VALID, "stream_url": "https://cctv.allowed.test/a.m3u8"})
    finally:
        app.config["STREAM_ALLOWED_HOSTS"] = []
    assert bad.status_code == 422
    assert good.status_code == 201


def test_duplicate_name_conflict(client, admin_headers):
    assert client.post("/api/cameras", headers=admin_headers, json=VALID).status_code == 201
    res = client.post("/api/cameras", headers=admin_headers, json={**VALID, "name": VALID["name"].upper()})
    assert res.status_code == 409
    assert res.get_json()["error"]["code"] == "duplicate_name"


def test_max_three_active_cameras(client, admin_headers, make_camera):
    for i in range(3):
        make_camera(name=f"Cam {i}")
    res = client.post("/api/cameras", headers=admin_headers, json=VALID)
    assert res.status_code == 409
    assert res.get_json()["error"]["code"] == "active_camera_limit"
    # Inactive camera may still be registered, but not activated.
    res = client.post("/api/cameras", headers=admin_headers, json={**VALID, "status": "inactive"})
    assert res.status_code == 201
    camera_id = res.get_json()["data"]["id"]
    assert client.put(f"/api/cameras/{camera_id}", headers=admin_headers,
                      json={"status": "active"}).status_code == 409
    # Updating an already-active camera does not trip the limit.
    assert client.put("/api/cameras/1", headers=admin_headers, json={"name": "Cam 0b"}).status_code == 200


def test_put_requires_some_field_and_no_nulls(client, admin_headers, make_camera):
    camera_id = make_camera()
    assert client.put(f"/api/cameras/{camera_id}", headers=admin_headers, json={}).status_code == 422
    assert client.put(f"/api/cameras/{camera_id}", headers=admin_headers,
                      json={"name": None}).status_code == 422


def test_filter_by_status(client, admin_headers, make_camera):
    make_camera(name="A")
    make_camera(name="B", status="inactive")
    res = client.get("/api/cameras?status=inactive", headers=admin_headers).get_json()
    assert [c["name"] for c in res["data"]] == ["B"]
    assert client.get("/api/cameras?status=weird", headers=admin_headers).status_code == 422
