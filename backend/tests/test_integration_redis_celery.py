"""End-to-end integration with a REAL Redis server and a REAL Celery worker.

Flow: generated video file -> OpenCV StreamReader -> Redis frame queue ->
Celery (Redis broker) -> detection task -> PostgreSQL -> Redis pub/sub -> SSE.

Only YOLO is faked (no weights available). Not a CCTV test; it does not prove
PT-01/PT-02 because real inference time is not included.

Run with:  TEST_REDIS_URL=redis://127.0.0.1:6379/15 pytest -m integration
"""
from __future__ import annotations

import json
import os
import threading
import time

import pytest
from sqlalchemy import func, select

from citysight import create_app
from citysight.extensions import db
from citysight.ingest import IngestSupervisor
from citysight.models import Camera, Detection, HourlyStat
from citysight.pipeline import camera_state
from citysight.pipeline.detector import VehicleDetector, set_detector
from citysight.pipeline.stream_reader import ReaderSettings, StreamReader
from citysight.redis_client import get_redis

from .fakes import FakeYolo
from .test_stream_reader import write_video

REDIS_URL = os.getenv("TEST_REDIS_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not REDIS_URL.startswith("redis://"), reason="TEST_REDIS_URL (real Redis) not set"),
]
CLASS_NAMES = {"car": "car", "motorcycle": "motorcycle", "bus": "bus", "truck": "truck"}


@pytest.fixture(scope="module")
def real_app(app):
    integration = create_app("testing", {
        "REDIS_URL": REDIS_URL, "CELERY_BROKER_URL": REDIS_URL, "SSE_MAX_SECONDS": 4,
    })
    get_redis(REDIS_URL).flushdb()
    yield integration
    get_redis(REDIS_URL).flushdb()
    app.extensions["celery"].set_default()  # restore the unit-test Celery app


@pytest.fixture(scope="module")
def worker(real_app):
    from celery.contrib.testing.worker import start_worker

    celery = real_app.extensions["celery"]
    with start_worker(celery, pool="threads", concurrency=3, queues=["detection", "stats"],
                      perform_ping_check=False, shutdown_timeout=10):
        yield celery


@pytest.fixture
def fake_yolo():
    model = FakeYolo([(2, 0.9), (2, 0.9), (3, 0.8), (5, 0.75)])  # 2 car, 1 motorcycle, 1 bus
    set_detector(VehicleDetector(model, CLASS_NAMES, confidence=0.7, iou=0.5))
    return model


def _cameras(real_app, n, tmp_path):
    ids = []
    with real_app.app_context():
        for i in range(n):
            video = tmp_path / f"cam{i}.avi"
            write_video(video, seconds=2)
            camera = Camera(name=f"Integrasi {i}", location="test", stream_url=str(video), status="active")
            db.session.add(camera)
            db.session.commit()
            ids.append((camera.id, str(video)))
    return ids


def test_three_cameras_end_to_end(real_app, worker, fake_yolo, tmp_path):
    cams = _cameras(real_app, 3, tmp_path)
    client = get_redis(REDIS_URL)
    sup = IngestSupervisor(real_app)
    settings = ReaderSettings(frame_interval=0.2, queue_max=10, jpeg_quality=80)
    readers = [StreamReader(cid, url, client, settings, on_frame=sup._schedule_detection) for cid, url in cams]

    duration = 6.0
    start = time.monotonic()
    for reader in readers:
        reader.start()
    time.sleep(duration)
    for reader in readers:
        reader.stop()
    for reader in readers:
        reader.join(5)
    time.sleep(1.0)  # let in-flight tasks finish
    elapsed = time.monotonic() - start

    with real_app.app_context():
        per_camera = dict(db.session.execute(
            select(Detection.camera_id, func.count()).group_by(Detection.camera_id)).all())
        sample = db.session.scalars(select(Detection).limit(1)).one()
        assert (sample.car_count, sample.motorcycle_count, sample.bus_count, sample.truck_count,
                sample.total_vehicle) == (2, 1, 1, 0, 4)
    states = camera_state.read_states(client, [cid for cid, _ in cams])
    print(f"\n[integration] {duration:.0f}s capture window, elapsed {elapsed:.1f}s")
    for cid, _ in cams:
        s = states[cid]
        print(f"[integration] camera {cid}: captured={s['frames_captured']} stored={per_camera.get(cid, 0)} "
              f"rate={per_camera.get(cid, 0) / duration:.2f}/s discarded={s['frames_discarded']} "
              f"stale={s['frames_stale']}")
        # Fake model is instant, so ~every captured frame should be stored.
        assert per_camera.get(cid, 0) >= 0.8 * s["frames_captured"]
        assert s["frames_captured"] >= 0.8 * duration / 0.2


def test_sse_receives_worker_events(real_app, worker, fake_yolo, tmp_path):
    (cid, url), = _cameras(real_app, 1, tmp_path)
    redis_client = get_redis(REDIS_URL)
    sup = IngestSupervisor(real_app)
    with real_app.app_context():
        from flask_jwt_extended import create_access_token

        from citysight.auth.passwords import hash_password
        from citysight.models import User

        user = User(username="sse", email="sse@example.test", role="operator",
                    password_hash=hash_password("Operator-pass-1"))
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=user)

    reader = StreamReader(cid, url, redis_client, ReaderSettings(), on_frame=sup._schedule_detection)

    def run_reader():
        time.sleep(0.5)
        reader.start()

    threading.Thread(target=run_reader).start()
    sent = time.time()
    res = real_app.test_client().get(f"/api/stream/detections?camera_id={cid}&access_token={token}",
                                     buffered=False)
    body = b"".join(res.response).decode()
    reader.stop()
    reader.join(5)
    events = [json.loads(line[6:]) for line in body.splitlines()
              if line.startswith("data: ") and '"timestamp"' in line]
    assert events, body
    assert all(e["camera_id"] == cid and e["total_vehicle"] == 4 for e in events)
    print(f"\n[integration] SSE delivered {len(events)} events in a {time.time() - sent:.1f}s window")


def test_aggregation_task_via_broker(real_app, worker):
    from datetime import datetime, timedelta, timezone

    from citysight.pipeline.detector import VehicleCounts
    from citysight.services.detection_service import save_detection

    hour = datetime(2026, 10, 22, 2, tzinfo=timezone.utc)
    with real_app.app_context():
        camera = Camera(name="Agg", location="x", stream_url="rtsp://cctv.example.test/a", status="inactive")
        db.session.add(camera)
        db.session.commit()
        for i, total in enumerate([1, 5]):
            save_detection(camera.id, hour + timedelta(minutes=i), VehicleCounts(car=total))
        camera_id = camera.id

    celery = worker
    for _ in range(2):  # twice: idempotent
        celery.send_task("citysight.aggregate_hourly_stats", queue="stats",
                         kwargs={"now_iso": (hour + timedelta(hours=1, minutes=5)).isoformat(),
                                 "lookback_hours": 1})
    deadline = time.monotonic() + 10
    rows = []
    while time.monotonic() < deadline:
        with real_app.app_context():
            rows = db.session.scalars(select(HourlyStat).where(HourlyStat.camera_id == camera_id)).all()
            db.session.remove()
        if rows:
            time.sleep(1)  # let the second run finish too
            break
        time.sleep(0.2)
    with real_app.app_context():
        rows = db.session.scalars(select(HourlyStat).where(HourlyStat.camera_id == camera_id)).all()
        assert [(r.avg_vehicle, r.max_vehicle, r.total_detections) for r in rows] == [(3.0, 5, 2)]
