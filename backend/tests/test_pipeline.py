"""Frame queue, YOLO class mapping and the Celery detection task.

YOLO is replaced by FakeYolo here: these tests check our counting/storage
logic, not model accuracy (accuracy = test AI-01 with real CCTV images).
"""
from __future__ import annotations

import json
import time

import cv2
import numpy as np
import pytest
from sqlalchemy import select

from citysight.extensions import db
from citysight.models import Detection
from citysight.pipeline import camera_state, frame_queue
from citysight.pipeline.detector import (ModelConfigError, ModelUnavailable, VehicleDetector, load_model,
                                         resolve_class_ids, set_detector)
from citysight.services.realtime import CHANNEL
from citysight.tasks.detection import detect_latest_frame

from .fakes import COCO_NAMES, FakeYolo

CLASS_NAMES = {"car": "car", "motorcycle": "motorcycle", "bus": "bus", "truck": "truck"}


def jpeg(value=0):
    ok, buf = cv2.imencode(".jpg", np.full((48, 64, 3), value, np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 80])
    assert ok
    return buf.tobytes()


# --- frame queue -----------------------------------------------------------

def test_queue_bounded_to_ten_latest(redis_client):
    evicted = [frame_queue.push_frame(redis_client, 1, float(i), b"x%d" % i, max_len=10) for i in range(15)]
    assert frame_queue.queue_length(redis_client, 1) == 10
    assert sum(evicted) == 5
    frame = frame_queue.take_latest(redis_client, 1)
    assert frame.captured_at == 14.0 and frame.jpeg == b"x14"
    assert frame.discarded == 9
    assert frame_queue.take_latest(redis_client, 1) is None  # older frames dropped, never re-processed


def test_queues_are_isolated_per_camera(redis_client):
    frame_queue.push_frame(redis_client, 1, 1.0, b"a", 10)
    frame_queue.push_frame(redis_client, 2, 2.0, b"b", 10)
    assert frame_queue.take_latest(redis_client, 2).jpeg == b"b"
    assert frame_queue.take_latest(redis_client, 1).jpeg == b"a"


def test_detection_slot_dedup(redis_client):
    assert frame_queue.claim_detection_slot(redis_client, 3)
    assert not frame_queue.claim_detection_slot(redis_client, 3)
    frame_queue.release_detection_slot(redis_client, 3)
    assert frame_queue.claim_detection_slot(redis_client, 3)


def test_frame_decode_rejects_truncated():
    with pytest.raises(ValueError):
        frame_queue.decode(b"123")


# --- detector ----------------------------------------------------------------

def test_class_ids_resolved_from_model_names():
    assert resolve_class_ids(COCO_NAMES, CLASS_NAMES) == {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def test_custom_model_label_mapping():
    names = {0: "mobil", 1: "motor", 2: "bus", 3: "truk"}
    mapping = resolve_class_ids(names, {"car": "mobil", "motorcycle": "motor", "bus": "bus", "truck": "truk"})
    assert mapping == {0: "car", 1: "motorcycle", 2: "bus", 3: "truck"}


def test_missing_class_fails_loudly():
    with pytest.raises(ModelConfigError, match="truck"):
        resolve_class_ids({0: "car", 1: "motorcycle", 2: "bus"}, CLASS_NAMES)


def test_detector_counts_vehicle_classes_only():
    model = FakeYolo([(2, 0.9), (2, 0.71), (3, 0.95), (3, 0.69), (5, 0.8), (7, 0.99), (0, 0.99), (9, 0.9)])
    counts = VehicleDetector(model, CLASS_NAMES, confidence=0.70, iou=0.50).detect(np.zeros((4, 4, 3)))
    assert (counts.car, counts.motorcycle, counts.bus, counts.truck, counts.total) == (2, 1, 1, 1, 5)
    kwargs = model.calls[0]
    assert kwargs["conf"] == 0.70 and kwargs["iou"] == 0.50
    assert kwargs["classes"] == [2, 3, 5, 7]
    assert kwargs["agnostic_nms"] is True


def test_missing_weights_are_not_downloaded(tmp_path):
    with pytest.raises(ModelUnavailable, match="automatic download is disabled"):
        load_model(str(tmp_path / "yolo11n.pt"))


# --- Celery detection task -------------------------------------------------------

@pytest.fixture
def fake_detector(app):
    model = FakeYolo([(2, 0.9), (3, 0.8), (3, 0.8), (7, 0.75)])
    set_detector(VehicleDetector(model, CLASS_NAMES, confidence=0.7, iou=0.5))
    return model


def test_task_stores_detection_and_publishes(app, redis_client, make_camera, fake_detector):
    camera_id = make_camera()
    pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(CHANNEL)
    captured = time.time()
    frame_queue.push_frame(redis_client, camera_id, captured - 0.4, jpeg(10), 10)
    frame_queue.push_frame(redis_client, camera_id, captured, jpeg(20), 10)
    frame_queue.claim_detection_slot(redis_client, camera_id)

    event = detect_latest_frame.apply(args=[camera_id]).get()

    assert event["camera_id"] == camera_id
    assert (event["car_count"], event["motorcycle_count"], event["bus_count"], event["truck_count"],
            event["total_vehicle"]) == (1, 2, 0, 1, 4)
    with app.app_context():
        rows = db.session.scalars(select(Detection)).all()
        assert len(rows) == 1
        assert abs(rows[0].timestamp.timestamp() - captured) < 1e-3  # capture time, not processing time
    message = None
    for _ in range(5):  # first call only consumes the subscribe confirmation
        message = message or pubsub.get_message(timeout=0.2)
    assert message is not None
    assert json.loads(message["data"]) == event
    assert not redis_client.exists(frame_queue.pending_key(camera_id))  # slot released
    state = camera_state.read_states(redis_client, [camera_id])[camera_id]
    assert state["frames_discarded"] == 1


def test_task_with_empty_queue_is_noop(app, make_camera, fake_detector):
    camera_id = make_camera()
    assert detect_latest_frame.apply(args=[camera_id]).get() is None
    assert fake_detector.calls == []


def test_task_drops_stale_frame(app, redis_client, make_camera, fake_detector):
    camera_id = make_camera()
    frame_queue.push_frame(redis_client, camera_id, time.time() - 60, jpeg(), 10)
    assert detect_latest_frame.apply(args=[camera_id]).get() is None
    with app.app_context():
        assert db.session.scalars(select(Detection)).all() == []
    assert camera_state.read_states(redis_client, [camera_id])[camera_id]["frames_stale"] == 1


def test_task_survives_missing_model(app, redis_client, make_camera, tmp_path):
    camera_id = make_camera()
    app.config["YOLO_MODEL_PATH"] = str(tmp_path / "missing.pt")
    frame_queue.push_frame(redis_client, camera_id, time.time(), jpeg(), 10)
    frame_queue.claim_detection_slot(redis_client, camera_id)
    result = detect_latest_frame.apply(args=[camera_id])
    assert result.successful() and result.get() is None
    state = camera_state.read_states(redis_client, [camera_id])[camera_id]
    assert "weights not found" in state["last_inference_error"]
    assert not redis_client.exists(frame_queue.pending_key(camera_id))


def test_task_survives_corrupt_frame(app, redis_client, make_camera, fake_detector):
    camera_id = make_camera()
    frame_queue.push_frame(redis_client, camera_id, time.time(), b"not-a-jpeg", 10)
    assert detect_latest_frame.apply(args=[camera_id]).successful()
    assert camera_state.read_states(redis_client, [camera_id])[camera_id]["last_inference_error"] == "ValueError"


def test_task_for_unknown_camera_does_not_crash(app, redis_client, fake_detector):
    frame_queue.push_frame(redis_client, 999, time.time(), jpeg(), 10)
    assert detect_latest_frame.apply(args=[999]).successful()


# --- regressions found while running real worker processes ------------------------

def test_task_class_is_picklable_for_spawn_pools():
    import pickle

    from citysight.celery_app import FlaskTask

    assert pickle.loads(pickle.dumps(FlaskTask)) is FlaskTask


def test_each_thread_gets_its_own_model(app, monkeypatch):
    import threading

    from citysight.pipeline import detector as detector_mod

    loads = []
    monkeypatch.setattr(detector_mod, "load_model", lambda path: loads.append(path) or FakeYolo())
    seen = []

    def work():
        first = detector_mod.get_detector(app.config)
        assert detector_mod.get_detector(app.config) is first  # cached per thread
        seen.append(first)

    threads = [threading.Thread(target=work) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(loads) == 3 and len({id(d) for d in seen}) == 3
