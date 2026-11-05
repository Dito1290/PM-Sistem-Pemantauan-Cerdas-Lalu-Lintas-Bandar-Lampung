"""Anomaly indications: high_density, camera_offline, API, SSE and Telegram."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests
from sqlalchemy import select

from citysight.extensions import db
from citysight.models import Anomaly, Camera, HourlyStat
from citysight.pipeline.detector import VehicleCounts
from citysight.services import anomaly_service, notifier
from citysight.services.detection_service import save_detection
from citysight.services.realtime import ANOMALY_CHANNEL
from citysight.timeutil import isoformat, utcnow

# 10:30 WIB. Defaults: ratio 2.0, at least 15 vehicles, 3 frames within 4 minutes.
T = datetime(2026, 11, 5, 3, 30, tzinfo=timezone.utc)


@pytest.fixture
def events(monkeypatch):
    sent = []
    monkeypatch.setattr(anomaly_service, "publish_anomaly", lambda _client, event: sent.append(event))
    return sent


def _baseline(app, camera_id, usual, hours):
    with app.app_context():
        for hour in hours:
            db.session.add(HourlyStat(camera_id=camera_id, hour_bucket=hour, avg_vehicle=usual,
                                      max_vehicle=int(usual) + 5, total_detections=60))
        db.session.commit()


def _same_hour_days(n):
    return [T.replace(minute=0) - timedelta(days=d) for d in range(1, n + 1)]


def _frame(app, camera_id, at, total, photo=None):
    with app.app_context():
        save_detection(camera_id, at, VehicleCounts(car=total))
        return anomaly_service.evaluate_density(camera_id, at, total, photo)


def _anomalies(app):
    with app.app_context():
        return [(a.camera_id, a.type, a.ended_at is None)
                for a in db.session.scalars(select(Anomaly).order_by(Anomaly.id))]


# --- high_density -------------------------------------------------------------

def test_density_starts_after_enough_full_frames_and_ends(app, make_camera, events):
    cam = make_camera()
    _baseline(app, cam, 10.0, _same_hour_days(3))  # usual 10 -> threshold 20

    assert _frame(app, cam, T - timedelta(minutes=2), 25) == []
    assert _frame(app, cam, T - timedelta(minutes=1), 26) == []  # only 2 frames so far
    started = _frame(app, cam, T, 30, photo=b"jpeg")
    assert [e["change"] for e in started] == ["started"]
    event = started[0]
    assert event["type"] == "high_density" and event["status"] == "active"
    assert event["started_at"] == "2026-11-05T03:28:00Z"  # first full frame, not detection time
    assert event["details"] == {"usual_vehicle": 10.0, "baseline_scope": "same_hour", "threshold": 20,
                                "peak_vehicle": 30, "frames": 3}
    assert "biasanya sekitar 10" in event["message"]

    assert _frame(app, cam, T + timedelta(minutes=1), 31) == []  # still active, peak updated
    for minute in (2, 3, 4):
        assert _frame(app, cam, T + timedelta(minutes=minute), 5) == []  # 31 still in the window
    ended = _frame(app, cam, T + timedelta(minutes=5), 5)
    assert [e["change"] for e in ended] == ["ended"]
    assert ended[0]["ended_at"] == "2026-11-05T03:35:00Z"
    assert ended[0]["details"]["peak_vehicle"] == 31
    assert [e["change"] for e in events] == ["started", "ended"]


def test_one_low_frame_keeps_density_closed(app, make_camera, events):
    cam = make_camera()
    _baseline(app, cam, 10.0, _same_hour_days(3))
    for minute, total in ((0, 25), (1, 19), (2, 25), (3, 25), (4, 25)):
        _frame(app, cam, T + timedelta(minutes=minute), total)
    assert _anomalies(app) == []  # the 19 at minute 1 is still inside the 4-minute window
    _frame(app, cam, T + timedelta(minutes=5), 25)
    assert _anomalies(app) == [(cam, "high_density", True)]


def test_density_needs_a_baseline(app, make_camera, events):
    cam = make_camera()
    _baseline(app, cam, 10.0, _same_hour_days(2))  # 2 hours are not enough
    with app.app_context():
        assert anomaly_service.density_baseline(cam, T) is None
    for minute in range(4):
        _frame(app, cam, T + timedelta(minutes=minute), 100)
    assert _anomalies(app) == [] and events == []


def test_baseline_falls_back_to_all_hours_and_min_vehicles(app, make_camera, events):
    cam = make_camera()
    other_hours = [T.replace(minute=0) - timedelta(hours=h) for h in (1, 2, 3)]
    _baseline(app, cam, 4.0, other_hours)
    _baseline(app, cam, 50.0, [T.replace(minute=0)])  # current hour is never part of the baseline
    with app.app_context():
        assert anomaly_service.density_baseline(cam, T) == (4.0, "all_hours")
        assert anomaly_service.density_threshold(4.0) == 15  # 2 x 4 = 8 is below the floor of 15
    for minute in range(3):
        _frame(app, cam, T + timedelta(minutes=minute), 14)
    assert _anomalies(app) == []
    for minute in range(3, 7):  # the last 14 leaves the window at minute 6
        _frame(app, cam, T + timedelta(minutes=minute), 15)
    assert _anomalies(app) == [(cam, "high_density", True)]


def test_same_hour_baseline_preferred(app, make_camera):
    cam = make_camera()
    _baseline(app, cam, 30.0, _same_hour_days(3))
    _baseline(app, cam, 2.0, [T.replace(minute=0) - timedelta(hours=h) for h in (1, 2, 3, 4)])
    with app.app_context():
        assert anomaly_service.density_baseline(cam, T) == (30.0, "same_hour")


def test_only_one_active_anomaly_per_camera_and_type(app, make_camera, events):
    cam = make_camera()
    with app.app_context():
        first = anomaly_service._start(cam, "high_density", T, "a", {"threshold": 20})
        second = anomaly_service._start(cam, "high_density", T, "b", {"threshold": 20})
        other = anomaly_service._start(cam, "camera_offline", T, "c", {})
    assert len(first) == 1 and second == [] and len(other) == 1
    assert len(_anomalies(app)) == 2


# --- camera_offline -----------------------------------------------------------

def _updated_at(app, cam):
    with app.app_context():
        return db.session.get(Camera, cam).updated_at


def test_offline_starts_after_limit_and_ends_on_new_frame(app, make_camera, events):
    cam = make_camera()
    added = _updated_at(app, cam)
    with app.app_context():
        assert anomaly_service.check_cameras(now=added + timedelta(minutes=4)) == []
        assert anomaly_service.check_cameras(now=added + timedelta(minutes=6), allow_start=False) == []
        started = anomaly_service.check_cameras(now=added + timedelta(minutes=6))
    assert [(e["change"], e["type"]) for e in started] == [("started", "camera_offline")]
    assert started[0]["message"].startswith("Kamera tidak mengirim gambar selama 6 menit.")
    assert "ingest tidak berjalan" in started[0]["message"]  # no Redis state at all

    with app.app_context():
        assert anomaly_service.check_cameras(now=added + timedelta(minutes=7)) == []  # already active
        save_detection(cam, added + timedelta(minutes=7, seconds=30), VehicleCounts(car=3))
        ended = anomaly_service.check_cameras(now=added + timedelta(minutes=8))
    assert [e["change"] for e in ended] == ["ended"]
    assert ended[0]["ended_at"] == isoformat(added + timedelta(minutes=7, seconds=30))


def test_offline_cause_from_stream_state(app, make_camera, redis_client, events):
    cam = make_camera()
    added = _updated_at(app, cam)
    redis_client.hset(f"camera:state:{cam}", mapping={
        "state": "reconnecting", "updated_at": time.time(), "last_error": "server lambat"})
    with app.app_context():
        started = anomaly_service.check_cameras(now=added + timedelta(minutes=10))
    assert "Sumber CCTV tidak bisa dibuka (server lambat)." in started[0]["message"]
    assert started[0]["details"]["stream_state"] == "reconnecting"


def test_offline_ends_density_and_inactive_camera_ends_all(app, make_camera, events):
    cam = make_camera()
    added = _updated_at(app, cam)
    with app.app_context():
        anomaly_service._start(cam, "high_density", added, "padat", {"threshold": 20})
        changes = anomaly_service.check_cameras(now=added + timedelta(minutes=6))
    assert [(e["type"], e["change"]) for e in changes] == [("high_density", "ended"), ("camera_offline", "started")]

    with app.app_context():
        db.session.get(Camera, cam).status = "inactive"
        db.session.commit()
        changes = anomaly_service.check_cameras(now=utcnow())
    assert [(e["type"], e["change"]) for e in changes] == [("camera_offline", "ended")]
    assert changes[0]["details"]["end_reason"] == "Kamera dinonaktifkan atau dihapus."
    assert all(not active for *_, active in _anomalies(app))


def test_check_task_waits_after_worker_start(app, make_camera, monkeypatch, events):
    from citysight.tasks import anomaly as task_mod

    make_camera()
    calls = []
    monkeypatch.setattr(anomaly_service, "check_cameras", lambda allow_start: calls.append(allow_start) or [])
    monkeypatch.setattr(task_mod, "_STARTED", time.monotonic())
    task_mod.check_anomalies.apply().get()
    monkeypatch.setattr(task_mod, "_STARTED", time.monotonic() - 3600)
    task_mod.check_anomalies.apply().get()
    assert calls == [False, True]


def test_density_failure_does_not_lose_the_detection(app, make_camera, redis_client, monkeypatch):
    import cv2
    import numpy as np

    from citysight.models import Detection
    from citysight.pipeline import frame_queue
    from citysight.pipeline.detector import VehicleDetector, set_detector
    from citysight.tasks.detection import detect_latest_frame

    from .fakes import FakeYolo

    cam = make_camera()
    set_detector(VehicleDetector(FakeYolo([(2, 0.9)]), {"car": "car", "motorcycle": "motorcycle",
                                                        "bus": "bus", "truck": "truck"}, confidence=0.5, iou=0.5))

    def boom(*_args):
        raise RuntimeError("anomaly bug")

    monkeypatch.setattr(anomaly_service, "evaluate_density", boom)
    _, buf = cv2.imencode(".jpg", np.zeros((32, 32, 3), np.uint8))
    frame_queue.push_frame(redis_client, cam, time.time(), buf.tobytes(), 10)
    event = detect_latest_frame.apply(args=[cam]).get()
    assert event is not None and event["total_vehicle"] == 1
    with app.app_context():
        assert len(db.session.scalars(select(Detection)).all()) == 1


# --- Telegram -----------------------------------------------------------------

class _Res:
    ok, status_code, text = True, 200, "{}"


def test_telegram_alert_with_photo_on_start(app, make_camera, monkeypatch, events):
    posts = []
    monkeypatch.setitem(app.config, "TELEGRAM_BOT_TOKEN", "123:secret")
    monkeypatch.setitem(app.config, "TELEGRAM_CHAT_ID", "-100")
    monkeypatch.setattr(notifier.requests, "post", lambda url, **kw: posts.append((url, kw)) or _Res())
    cam = make_camera(name="Tugu Adipura")
    _baseline(app, cam, 10.0, _same_hour_days(3))
    for minute, total in ((0, 25), (1, 25), (2, 25)):
        _frame(app, cam, T + timedelta(minutes=minute), total, photo=b"jpeg-bytes")
    for minute in range(3, 8):
        _frame(app, cam, T + timedelta(minutes=minute), 2, photo=b"jpeg-bytes")

    assert [url.rsplit("/", 1)[1] for url, _ in posts] == ["sendPhoto", "sendMessage"]
    start = posts[0][1]
    assert start["files"]["photo"][1] == b"jpeg-bytes"
    assert "Kamera: Tugu Adipura" in start["data"]["caption"] and "10:30 WIB" in start["data"]["caption"]
    assert "SELESAI" in posts[1][1]["json"]["text"]


def test_telegram_failure_is_logged_without_token(app, monkeypatch):
    def fail(url, **_kw):
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}")

    logged = []
    monkeypatch.setattr(notifier.requests, "post", fail)
    monkeypatch.setattr(notifier.log, "warning", lambda msg, *args: logged.append(msg % args))
    config = {"TELEGRAM_BOT_TOKEN": "123:secret", "TELEGRAM_CHAT_ID": "-100"}
    assert notifier.send_telegram(config, "x") is False
    assert logged == ["Telegram alert not sent: ConnectionError"]
    assert notifier.send_telegram({"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}, "x") is False


# --- API and SSE --------------------------------------------------------------

def test_list_anomalies_api(app, client, operator_headers, make_camera, events):
    a, b = make_camera(name="A"), make_camera(name="B")
    with app.app_context():
        anomaly_service._start(a, "high_density", T, "padat", {"threshold": 20})
        old = anomaly_service._start(b, "camera_offline", T - timedelta(hours=1), "mati", {})
        anomaly_service._end(db.session.get(Anomaly, old[0]["id"]), T, reason="pulih")

    assert client.get("/api/anomalies").status_code == 401
    body = client.get("/api/anomalies", headers=operator_headers).get_json()
    assert [(x["camera_name"], x["type"], x["status"]) for x in body["data"]] == [
        ("A", "high_density", "active"), ("B", "camera_offline", "ended")]
    assert body["meta"]["total"] == 2 and body["meta"]["semantics"] == "indication"

    active = client.get("/api/anomalies?status=active", headers=operator_headers).get_json()["data"]
    assert [x["camera_id"] for x in active] == [a]
    by_cam = client.get(f"/api/anomalies?camera_id={b}&type=camera_offline", headers=operator_headers)
    assert [x["camera_id"] for x in by_cam.get_json()["data"]] == [b]
    assert client.get("/api/anomalies?camera_id=99", headers=operator_headers).status_code == 404
    assert client.get("/api/anomalies?status=open", headers=operator_headers).status_code == 422


def test_sse_streams_anomaly_events(client, redis_client, tokens, make_camera):
    a, b = make_camera(name="A"), make_camera(name="B")

    def publish():
        time.sleep(0.8)
        redis_client.publish(ANOMALY_CHANNEL, json.dumps({"id": 1, "camera_id": b, "change": "started"}))
        redis_client.publish(ANOMALY_CHANNEL, json.dumps({"id": 2, "camera_id": a, "change": "started"}))

    threading.Thread(target=publish).start()
    res = client.get(f"/api/stream/detections?camera_id={a}&access_token={tokens['operator']}", buffered=False)
    body = b"".join(res.response).decode()
    assert "event: anomaly" in body and "id: anomaly-2-started" in body
    assert "anomaly-1-" not in body
