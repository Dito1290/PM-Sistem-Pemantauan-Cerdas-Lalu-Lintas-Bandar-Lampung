"""Operator review of anomalies, stored photos, and checks switched off at certain hours."""
from __future__ import annotations

import json
from datetime import datetime, time, timezone

import pytest

from citysight.extensions import db
from citysight.models import Anomaly
from citysight.pipeline import stopped_vehicle as sv
from citysight.services import anomaly_service

T = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
ROAD = [[0.0, 0.5], [1.0, 0.5], [1.0, 1.0], [0.0, 1.0]]


@pytest.fixture
def events(monkeypatch):
    sent = []
    monkeypatch.setattr(anomaly_service, "publish_anomaly", lambda _client, event: sent.append(event))
    return sent


def _open(app, cam, type_="people_on_road", photo=None):
    with app.app_context():
        return anomaly_service._start(cam, type_, T, "contoh", {"people": 3}, photo)[0]["id"]


# --- schedule -------------------------------------------------------------------

def test_check_switched_off_only_at_night(tmp_path):
    path = tmp_path / "zones.json"
    path.write_text(json.dumps({"2": {"areas": [ROAD], "disabled_hours": {"stopped_vehicle": ["18:00-06:00"]}}}))
    zones = sv.Zones(str(path))
    assert zones.disabled(2, time(19, 30)) == {"stopped_vehicle"}
    assert zones.disabled(2, time(2, 0)) == {"stopped_vehicle"}   # span runs past midnight
    assert zones.disabled(2, time(12, 0)) == set()
    assert zones.disabled(2, time(6, 0)) == set()                  # end is exclusive
    assert zones.disabled(2) == set()                               # no time given: only "disabled"


# --- review ---------------------------------------------------------------------

def test_operator_reviews_an_anomaly(app, client, operator_headers, make_camera, events):
    cam = make_camera(name="Underpass Unila")
    anomaly_id = _open(app, cam)
    assert client.post(f"/api/anomalies/{anomaly_id}/review", json={"verdict": "false"}).status_code == 401

    res = client.post(f"/api/anomalies/{anomaly_id}/review", headers=operator_headers,
                      json={"verdict": "false", "note": "parkir nongkrong"})
    assert res.status_code == 200
    review = res.get_json()["data"]["review"]
    assert (review["verdict"], review["note"], review["by"]) == ("false", "parkir nongkrong", "operator")
    assert events[-1]["change"] == "reviewed"

    # A second review replaces the first.
    res = client.post(f"/api/anomalies/{anomaly_id}/review", headers=operator_headers, json={"verdict": "true"})
    assert res.get_json()["data"]["review"]["verdict"] == "true"
    with app.app_context():
        assert db.session.get(Anomaly, anomaly_id).review_note is None


def test_review_validation(client, operator_headers, app, make_camera, events):
    anomaly_id = _open(app, make_camera())
    assert client.post("/api/anomalies/999/review", headers=operator_headers,
                       json={"verdict": "true"}).status_code == 404
    assert client.post(f"/api/anomalies/{anomaly_id}/review", headers=operator_headers,
                       json={"verdict": "maybe"}).status_code == 422
    assert client.post(f"/api/anomalies/{anomaly_id}/review", headers=operator_headers,
                       json={"verdict": "true", "note": "x" * 501}).status_code == 422


def test_review_does_not_send_telegram(app, client, operator_headers, make_camera, monkeypatch, events):
    sent = []
    monkeypatch.setitem(app.config, "TELEGRAM_BOT_TOKEN", "123:secret")
    monkeypatch.setitem(app.config, "TELEGRAM_CHAT_ID", "-100")
    monkeypatch.setattr(anomaly_service.notifier, "send_telegram", lambda *a, **k: sent.append(a))
    anomaly_id = _open(app, make_camera())
    sent.clear()
    client.post(f"/api/anomalies/{anomaly_id}/review", headers=operator_headers, json={"verdict": "true"})
    assert sent == []


def test_list_filters_by_review_and_summary(app, client, operator_headers, make_camera, events):
    a, b = make_camera(name="A"), make_camera(name="B")
    first, second = _open(app, a), _open(app, a, "stopped_vehicle")
    third = _open(app, b)
    client.post(f"/api/anomalies/{first}/review", headers=operator_headers, json={"verdict": "true"})
    client.post(f"/api/anomalies/{second}/review", headers=operator_headers, json={"verdict": "false"})

    pending = client.get("/api/anomalies?review=pending", headers=operator_headers).get_json()["data"]
    assert [x["id"] for x in pending] == [third]
    wrong = client.get("/api/anomalies?review=false", headers=operator_headers).get_json()["data"]
    assert [x["id"] for x in wrong] == [second]

    res = client.get("/api/anomalies/review-summary?from=2026-11-24&to=2026-11-24", headers=operator_headers)
    rows = {(r["camera_name"], r["type"]): r for r in res.get_json()["data"]}
    assert rows[("A", "people_on_road")] == {"camera_id": a, "camera_name": "A", "type": "people_on_road",
                                             "alerts": 1, "reviewed": 1, "correct": 1, "precision": 1.0}
    assert rows[("A", "stopped_vehicle")]["precision"] == 0.0
    assert rows[("B", "people_on_road")]["reviewed"] == 0 and rows[("B", "people_on_road")]["precision"] is None
    assert client.get("/api/anomalies/review-summary?from=2026-11-25&to=2026-11-24",
                      headers=operator_headers).status_code == 422


# --- photos ---------------------------------------------------------------------

def test_photo_is_kept_and_served(app, client, operator_headers, make_camera, monkeypatch, tmp_path, events):
    monkeypatch.setitem(app.config, "ANOMALY_PHOTO_DIR", str(tmp_path / "photos"))
    with_photo = _open(app, make_camera(name="A"), photo=b"\xff\xd8jpeg")
    without = _open(app, make_camera(name="B"))

    listed = {x["id"]: x for x in client.get("/api/anomalies", headers=operator_headers).get_json()["data"]}
    assert listed[with_photo]["photo_url"] == f"/api/anomalies/{with_photo}/photo"
    assert listed[without]["photo_url"] is None

    res = client.get(f"/api/anomalies/{with_photo}/photo", headers=operator_headers)
    assert res.status_code == 200 and res.mimetype == "image/jpeg" and res.data == b"\xff\xd8jpeg"
    assert client.get(f"/api/anomalies/{without}/photo", headers=operator_headers).status_code == 404
    assert client.get(f"/api/anomalies/{with_photo}/photo").status_code == 401
