"""People on the road: detector change (people kept apart from vehicles), monitor, anomaly lifecycle."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest

from citysight.pipeline import people_on_road as pr
from citysight.pipeline import stopped_vehicle as sv
from citysight.pipeline.detector import VehicleDetector
from citysight.services import anomaly_service

from .fakes import FakeYolo

CLASSES = {"car": "car", "motorcycle": "motorcycle", "bus": "bus", "truck": "truck"}
ROAD = [[0.0, 0.5], [1.0, 0.5], [1.0, 1.0], [0.0, 1.0]]
FPS = 4


def person(x: float, y: float = 0.70) -> dict:
    """Standing person with feet at (x + 0.01, y)."""
    return {"category": "person", "box": [x, y - 0.10, x + 0.02, y]}


MOTOR = {"category": "motorcycle", "box": [0.50, 0.65, 0.56, 0.75]}
RIDER = {"category": "person", "box": [0.51, 0.62, 0.55, 0.72]}  # mostly inside the motorcycle box


@pytest.fixture(autouse=True)
def _fresh_state():
    pr.reset()
    sv.reset()
    yield
    pr.reset()
    sv.reset()


# --- detector -------------------------------------------------------------------

def test_people_are_detected_but_never_counted_as_vehicles():
    model = FakeYolo([(3, 0.9, MOTOR["box"]), (0, 0.8, RIDER["box"]), (0, 0.7, [0.1, 0.6, 0.12, 0.7])])
    counts, boxes = VehicleDetector(model, CLASSES, confidence=0.25, iou=0.5,
                                    person_label="person").detect_with_boxes(None)
    assert (counts.motorcycle, counts.total) == (1, 1)
    assert sorted(b["category"] for b in boxes) == ["motorcycle", "person", "person"]
    call = model.calls[0]
    assert 0 in call["classes"] and call["agnostic_nms"] is False  # rider must not erase the motorcycle


def test_vehicle_only_agnostic_nms_still_merges_car_and_truck_labels():
    overlap_car, overlap_truck = [0.20, 0.60, 0.40, 0.80], [0.21, 0.60, 0.41, 0.81]
    model = FakeYolo([(2, 0.9, overlap_car), (7, 0.6, overlap_truck), (0, 0.8, [0.25, 0.55, 0.30, 0.75])])
    counts, boxes = VehicleDetector(model, CLASSES, confidence=0.25, iou=0.5,
                                    person_label="person").detect_with_boxes(None)
    assert (counts.car, counts.truck) == (1, 0)  # same as agnostic NMS inside predict()
    assert [b["category"] for b in boxes] == ["car", "person"]


def test_without_person_label_detector_behaves_as_before():
    model = FakeYolo([(2, 0.9), (0, 0.9)])
    counts, boxes = VehicleDetector(model, CLASSES, confidence=0.25, iou=0.5).detect_with_boxes(None)
    assert counts.total == 1 and [b["category"] for b in boxes] == ["car"]
    assert 0 not in model.calls[0]["classes"] and model.calls[0]["agnostic_nms"] is True


def test_model_without_person_label_disables_people():
    names = {0: "car", 1: "motorcycle", 2: "bus", 3: "truck"}
    detector = VehicleDetector(FakeYolo(names=names), CLASSES, confidence=0.25, iou=0.5, person_label="person")
    assert detector.person_id is None


# --- monitor ------------------------------------------------------------------

def feed(monitor, seconds, boxes, start=0.0):
    out = None
    for i in range(int(seconds * FPS)):
        out = monitor.update(start + i / FPS, boxes(i) if callable(boxes) else boxes, ROAD)
    return out


def test_group_of_people_staying_on_the_road_is_reported():
    monitor = pr.PeopleOnRoadMonitor(min_people=3, seconds=10)
    crowd = [person(0.30), person(0.35), person(0.40), person(0.45)]
    assert feed(monitor, 8, crowd) is None              # not long enough yet
    report = feed(monitor, 4, crowd, start=8)
    assert report["people"] == 4 and len(report["boxes"]) == 4 and report["seconds"] >= 9


def test_riders_are_not_people_on_foot():
    monitor = pr.PeopleOnRoadMonitor(min_people=1, seconds=10)
    assert feed(monitor, 20, [MOTOR, RIDER]) is None


def test_people_on_the_pavement_are_ignored():
    monitor = pr.PeopleOnRoadMonitor(min_people=3, seconds=10)
    pavement = [person(0.30, y=0.40), person(0.35, y=0.40), person(0.40, y=0.40)]  # feet above the zone
    assert feed(monitor, 20, pavement) is None


def test_pedestrians_crossing_for_a_few_seconds_are_not_reported():
    monitor = pr.PeopleOnRoadMonitor(min_people=3, seconds=10)
    group = [person(0.30), person(0.35), person(0.40)]
    # A group crosses for 3 s every 15 s.
    assert feed(monitor, 60, lambda i: group if (i / FPS) % 15 < 3 else []) is None


def test_one_frame_with_fewer_people_does_not_reset_the_count():
    monitor = pr.PeopleOnRoadMonitor(min_people=3, seconds=10)
    crowd = [person(0.30), person(0.35), person(0.40)]
    report = feed(monitor, 12, lambda i: crowd[:2] if i % 10 == 5 else crowd)  # someone hidden now and then
    assert report is not None


# --- anomaly lifecycle ----------------------------------------------------------

T0 = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def events(monkeypatch):
    sent = []
    monkeypatch.setattr(anomaly_service, "publish_anomaly", lambda _client, event: sent.append(event))
    return sent


def _run(app, cam, monitor, seconds, boxes, start):
    changes = []
    with app.app_context():
        for i in range(int(seconds * FPS)):
            t = start + i / FPS
            report = monitor.update(t, boxes, ROAD)
            at = datetime.fromtimestamp(T0.timestamp() + t, tz=timezone.utc)
            changes += anomaly_service.evaluate_people(cam, at, report, monitor, monitor_created=False)
    return changes


def test_people_on_road_anomaly_starts_and_ends(app, make_camera, events):
    cam = make_camera()
    monitor = pr.PeopleOnRoadMonitor(min_people=3, seconds=10)
    crowd = [person(0.30), person(0.35), person(0.40)]
    started = _run(app, cam, monitor, 11, crowd, start=0)
    assert [(e["change"], e["type"]) for e in started] == [("started", "people_on_road")]
    assert started[0]["message"].startswith("Orang di badan jalan: 3 orang berada di lajur jalan")
    ended = _run(app, cam, monitor, 35, [], start=11)
    assert [e["change"] for e in ended] == ["ended"]
    assert ended[0]["details"]["end_reason"] == "Orang sudah tidak berada di lajur jalan."


def test_worker_task_sends_people_to_their_own_monitor_only(app, make_camera, redis_client, monkeypatch, tmp_path):
    import cv2
    import numpy as np

    from citysight.pipeline import frame_queue
    from citysight.pipeline.detector import set_detector
    from citysight.tasks.detection import detect_latest_frame

    cam = make_camera()
    zones = tmp_path / "zones.json"
    zones.write_text(json.dumps({str(cam): ROAD}))
    config = detect_latest_frame.app.flask_app.config
    monkeypatch.setitem(config, "ANOMALY_ZONES_FILE", str(zones))
    monkeypatch.setitem(config, "YOLO_PERSON_CLASS", "person")
    set_detector(VehicleDetector(FakeYolo([(2, 0.9, [0.1, 0.6, 0.2, 0.7]), (0, 0.9, [0.5, 0.6, 0.52, 0.7])]),
                                 CLASSES, confidence=0.25, iou=0.5, person_label="person"))
    _, buf = cv2.imencode(".jpg", np.zeros((32, 32, 3), np.uint8))
    frame_queue.push_frame(redis_client, cam, time.time(), buf.tobytes(), 10)
    event = detect_latest_frame.apply(args=[cam]).get()
    assert event["total_vehicle"] == 1  # the person is not a vehicle
    stopped = sv._monitors[cam]
    assert [c.category for c in stopped.candidates] == ["car"]  # a standing person is not a stopped vehicle
    assert len(pr._monitors[cam].people) == 1  # but is followed as a person on the road


def test_people_walking_along_the_road_do_not_count_however_long():
    # Camera 2, 16:49: three people walked along the edge of the road for over 10 s.
    monitor = pr.PeopleOnRoadMonitor(min_people=3, seconds=10)
    report = feed(monitor, 60, lambda i: [person(0.05 + 0.004 * i + d) for d in (0.0, 0.05, 0.10)])
    assert report is None


def test_group_crossing_within_the_time_limit_is_not_reported():
    # Camera 1, 17:09: school children crossing at the zebra crossing (about 20 s).
    monitor = pr.PeopleOnRoadMonitor(min_people=3, seconds=30)
    group = [person(0.30), person(0.35), person(0.40)]
    assert feed(monitor, 20, group) is None
    assert feed(monitor, 40, [], start=20) is None


def test_people_moving_a_little_around_a_spot_still_count():
    # Helpers around a casualty shift around but stay near the same place.
    monitor = pr.PeopleOnRoadMonitor(min_people=3, seconds=10)
    report = feed(monitor, 12, lambda i: [person(0.30 + 0.01 * (i % 3)), person(0.35), person(0.40 - 0.01 * (i % 2))])
    assert report is not None and report["people"] == 3


def test_camera_can_switch_off_a_check(tmp_path):
    path = tmp_path / "zones.json"
    path.write_text(json.dumps({"1": {"areas": [ROAD], "disabled": ["stopped_vehicle"]}, "2": ROAD}))
    zones = sv.Zones(str(path))
    assert zones.get(1) == [ROAD] and zones.disabled(1) == {"stopped_vehicle"}
    assert zones.get(2) == [ROAD] and zones.disabled(2) == set()
