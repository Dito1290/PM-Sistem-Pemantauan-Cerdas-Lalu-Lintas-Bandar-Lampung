"""Stopped-vehicle indication: monitor logic, zones, anomaly lifecycle, worker hook."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from citysight.extensions import db
from citysight.models import Anomaly
from citysight.pipeline import stopped_vehicle as sv
from citysight.services import anomaly_service

# Whole lower half of the frame is road; boxes are [x1, y1, x2, y2] relative to the frame.
ROAD = [[0.0, 0.5], [1.0, 0.5], [1.0, 1.0], [0.0, 1.0]]
PARKED = {"category": "car", "box": [0.40, 0.60, 0.50, 0.70]}
FPS = 4


def moving_car(step: int) -> dict:
    """A car crossing the road, a full box width further every frame."""
    x = (step * 0.06) % 0.9
    return {"category": "car", "box": [x, 0.80, x + 0.05, 0.88]}


def run(monitor, seconds, *, with_parked=True, with_traffic=True, start=0.0, zone=ROAD):
    out = []
    for i in range(int(seconds * FPS)):
        boxes = ([PARKED] if with_parked else []) + ([moving_car(i)] if with_traffic else [])
        out = monitor.update(start + i / FPS, boxes, zone)
    return out


@pytest.fixture(autouse=True)
def _fresh_state():
    sv.reset()
    yield
    sv.reset()


# --- monitor ------------------------------------------------------------------

def test_vehicle_still_while_traffic_moves_is_reported_after_limit():
    monitor = sv.StoppedVehicleMonitor(stop_seconds=60)
    assert run(monitor, 59) == []
    stopped = run(monitor, 3, start=59)
    assert [(v["category"], v["box"]) for v in stopped] == [("car", PARKED["box"])]
    assert stopped[0]["stopped_seconds"] >= 60


def test_queue_without_moving_traffic_is_not_reported():
    monitor = sv.StoppedVehicleMonitor(stop_seconds=60)
    assert run(monitor, 120, with_traffic=False) == []  # red light or jam: nothing moves


def test_vehicle_outside_the_road_zone_is_ignored():
    monitor = sv.StoppedVehicleMonitor(stop_seconds=60)
    kerb = [[0.0, 0.75], [1.0, 0.75], [1.0, 1.0], [0.0, 1.0]]  # parked car's wheels at y=0.70 are outside
    assert run(monitor, 120, zone=kerb) == []


def test_busy_spot_driven_over_by_many_cars_is_not_a_stopped_vehicle():
    monitor = sv.StoppedVehicleMonitor(stop_seconds=60)
    out = []
    for i in range(120 * FPS):
        boxes = [moving_car(i)]
        if i % 4 == 0:  # a different car on the same spot one frame in four
            boxes.append(PARKED)
        out = monitor.update(i / FPS, boxes, ROAD)
    assert out == []


def test_short_occlusion_keeps_the_stopped_time():
    monitor = sv.StoppedVehicleMonitor(stop_seconds=60)
    run(monitor, 40)
    run(monitor, 5, with_parked=False, start=40)   # a bus hides it for 5 s
    assert run(monitor, 20, start=45) != []          # still counted from the start


def test_vehicle_that_drives_away_is_forgotten():
    monitor = sv.StoppedVehicleMonitor(stop_seconds=60)
    assert run(monitor, 70) != []
    assert run(monitor, sv.FORGET_SECONDS + 2, with_parked=False, start=70) == []


def test_point_in_zone_uses_wheel_position():
    assert sv.in_zone(ROAD, [0.1, 0.40, 0.2, 0.55])       # top above the zone, wheels inside
    assert not sv.in_zone(ROAD, [0.1, 0.10, 0.2, 0.45])


def test_zones_file_is_reloaded_when_changed(tmp_path):
    path = tmp_path / "zones.json"
    zones = sv.Zones(str(path))
    assert zones.get(1) is None  # no file: nothing is checked
    path.write_text(json.dumps({"1": ROAD, "2": [[0, 0], [1, 1]]}))
    assert zones.get(1) == [ROAD] and zones.get(2) is None  # 2 points is not a zone
    time.sleep(0.05)
    path.write_text(json.dumps({"1": ROAD[:3]}))
    import os
    os.utime(path, (time.time() + 5, time.time() + 5))
    assert zones.get(1) == [ROAD[:3]]


# --- anomaly lifecycle ----------------------------------------------------------

T0 = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def events(monkeypatch):
    sent = []
    monkeypatch.setattr(anomaly_service, "publish_anomaly", lambda _client, event: sent.append(event))
    return sent


def _feed(app, cam, monitor, seconds, *, start, created=False, **kw):
    """Feed frames through monitor + evaluate_stopped like the worker does."""
    changes = []
    with app.app_context():
        for i in range(int(seconds * FPS)):
            t = start + i / FPS
            boxes = ([PARKED] if kw.get("with_parked", True) else []) + [moving_car(i)]
            stopped = monitor.update(t, boxes, ROAD)
            at = datetime.fromtimestamp(T0.timestamp() + t, tz=timezone.utc)
            changes += anomaly_service.evaluate_stopped(cam, at, stopped, monitor,
                                                        monitor_created=created and i == 0)
    return changes


def test_stopped_vehicle_anomaly_starts_and_ends(app, make_camera, events):
    cam = make_camera()
    monitor = sv.StoppedVehicleMonitor(stop_seconds=60)
    started = _feed(app, cam, monitor, 62, start=0)
    assert [(e["change"], e["type"]) for e in started] == [("started", "stopped_vehicle")]
    assert started[0]["message"].startswith("Kendaraan berhenti tidak wajar: mobil diam sekitar 1 menit")
    assert started[0]["details"]["vehicles"][0]["box"] == PARKED["box"]

    # Car drives away: indication ends once nothing was reported for STOPPED_END_SECONDS.
    ended = _feed(app, cam, monitor, 40, start=62, with_parked=False)
    assert [e["change"] for e in ended] == ["ended"]
    assert ended[0]["details"]["end_reason"] == "Kendaraan sudah bergerak atau tidak terlihat lagi."
    assert [e["change"] for e in events] == ["started", "ended"]


def test_worker_restart_closes_an_indication_it_cannot_follow(app, make_camera, events):
    cam = make_camera()
    _feed(app, cam, sv.StoppedVehicleMonitor(stop_seconds=60), 62, start=0)
    fresh = sv.StoppedVehicleMonitor(stop_seconds=60)  # state lost
    changes = _feed(app, cam, fresh, 1, start=100, created=True)
    assert [(e["change"], e["details"].get("end_reason")) for e in changes] == [
        ("ended", "Pemantauan dimulai ulang, indikasi ditutup.")]


def test_telegram_photo_marks_the_stopped_vehicle(app, make_camera, events, monkeypatch):
    import cv2
    import numpy as np

    sent = []
    monkeypatch.setitem(app.config, "TELEGRAM_BOT_TOKEN", "123:secret")
    monkeypatch.setitem(app.config, "TELEGRAM_CHAT_ID", "-100")
    monkeypatch.setattr(anomaly_service.notifier, "send_telegram",
                        lambda _cfg, text, photo=None: sent.append((text, photo)))
    cam = make_camera(name="Tugu Adipura")
    monitor = sv.StoppedVehicleMonitor(stop_seconds=1)
    _, buf = cv2.imencode(".jpg", np.zeros((100, 200, 3), np.uint8))
    with app.app_context():
        for i in range(12):
            stopped = monitor.update(i / FPS, [PARKED, moving_car(i)], ROAD)
            anomaly_service.evaluate_stopped(cam, T0, stopped, monitor, monitor_created=False,
                                             photo_jpeg=buf.tobytes())
    text, photo = sent[0]
    assert "Kendaraan berhenti tidak wajar" in text
    marked = cv2.imdecode(np.frombuffer(photo, np.uint8), cv2.IMREAD_COLOR)
    assert marked[60, 80, 2] > 200  # red box drawn at the parked car's left edge (x=0.40, y=0.60)


def test_worker_task_feeds_the_monitor_only_for_cameras_with_a_zone(app, make_camera, redis_client,
                                                                    monkeypatch, tmp_path):
    import cv2
    import numpy as np

    from citysight.pipeline import frame_queue
    from citysight.pipeline.detector import VehicleDetector, set_detector
    from citysight.tasks.detection import detect_latest_frame

    from .fakes import FakeYolo

    with_zone, without_zone = make_camera(name="A"), make_camera(name="B")
    zones = tmp_path / "zones.json"
    zones.write_text(json.dumps({str(with_zone): [[0, 0], [1, 0], [1, 1], [0, 1]]}))
    task_config = detect_latest_frame.app.flask_app.config
    monkeypatch.setitem(task_config, "ANOMALY_ZONES_FILE", str(zones))
    set_detector(VehicleDetector(FakeYolo([(2, 0.9)]), {"car": "car", "motorcycle": "motorcycle",
                                                        "bus": "bus", "truck": "truck"}, confidence=0.5, iou=0.5))
    _, buf = cv2.imencode(".jpg", np.zeros((32, 32, 3), np.uint8))
    for cam in (with_zone, without_zone):
        frame_queue.push_frame(redis_client, cam, time.time(), buf.tobytes(), 10)
        detect_latest_frame.apply(args=[cam]).get()
    assert set(sv._monitors) == {with_zone}
    assert sv._monitors[with_zone].frame == 1
    with app.app_context():
        assert db.session.scalars(select(Anomaly)).all() == []


def test_queue_in_one_direction_is_not_reported_while_the_other_direction_flows():
    # Camera 1, 2026-11-24: the outbound carriageway queued while inbound traffic
    # flowed; with one zone for both, a queued truck was reported as stopped.
    outbound = [[0.0, 0.5], [0.45, 0.5], [0.45, 1.0], [0.0, 1.0]]
    inbound = [[0.55, 0.5], [1.0, 0.5], [1.0, 1.0], [0.55, 1.0]]
    queued = {"category": "truck", "box": [0.10, 0.60, 0.20, 0.72]}

    def inbound_car(step):
        x = 0.56 + (step * 0.06) % 0.38
        return {"category": "car", "box": [x, 0.80, x + 0.05, 0.88]}

    split = sv.StoppedVehicleMonitor(stop_seconds=60)
    single = sv.StoppedVehicleMonitor(stop_seconds=60)
    for i in range(70 * FPS):
        boxes = [queued, inbound_car(i)]
        out_split = split.update(i / FPS, boxes, [outbound, inbound])
        out_single = single.update(i / FPS, boxes, ROAD)
    assert out_split == []                    # nothing moves in the truck's own direction
    assert [v["category"] for v in out_single] == ["truck"]  # the old single zone reported it


def test_vehicle_cut_off_by_the_bottom_of_the_frame_is_in_the_zone():
    assert sv.in_zone(ROAD, [0.10, 0.80, 0.30, 1.0])  # zone drawn down to the frame edge


def test_several_vehicles_standing_together_is_a_jam_not_a_breakdown():
    # Camera 1 at school pick-up time: a row of motorcycles stood still while others
    # threaded past. One or two standing vehicles are still reported.
    row = [{"category": "motorcycle", "box": [0.60 + 0.08 * k, 0.60, 0.66 + 0.08 * k, 0.70]} for k in range(3)]
    monitor = sv.StoppedVehicleMonitor(stop_seconds=60)
    out = None
    for i in range(70 * FPS):
        out = monitor.update(i / FPS, row + [moving_car(i)], ROAD)
    assert out == []
    pair = sv.StoppedVehicleMonitor(stop_seconds=60)
    for i in range(70 * FPS):
        out = pair.update(i / FPS, row[:2] + [moving_car(i)], ROAD)
    assert len(out) == 2  # e.g. a bus stopping with a car stuck behind it


def test_end_of_a_kerbside_row_is_not_reported_even_if_the_rest_is_outside_the_zone():
    # 16:58: two pick-up motorcycles at the end of a long kerbside row were inside
    # the zone; the rest of the row stood just outside it.
    lane = [[0.0, 0.5], [0.70, 0.5], [0.70, 1.0], [0.0, 1.0]]
    inside = {"category": "motorcycle", "box": [0.62, 0.60, 0.68, 0.70]}
    kerb = [{"category": "motorcycle", "box": [0.72 + 0.07 * k, 0.60, 0.78 + 0.07 * k, 0.70]} for k in range(3)]
    monitor = sv.StoppedVehicleMonitor(stop_seconds=60)
    out = None
    for i in range(70 * FPS):
        out = monitor.update(i / FPS, [inside] + kerb + [moving_car(i)], lane)
    assert out == []
    alone = sv.StoppedVehicleMonitor(stop_seconds=60)
    for i in range(70 * FPS):
        out = alone.update(i / FPS, [inside, moving_car(i)], lane)
    assert [v["box"] for v in out] == [inside["box"]]  # on its own it is still reported


def test_vehicle_stops_being_reported_once_its_spot_is_taken_out_of_the_zone():
    monitor = sv.StoppedVehicleMonitor(stop_seconds=60)
    assert run(monitor, 62) != []                      # parked in the zone: reported
    narrowed = [[0.0, 0.75], [1.0, 0.75], [1.0, 1.0], [0.0, 1.0]]  # the parked car's spot is now outside
    assert run(monitor, 2, start=62, zone=narrowed) == []
