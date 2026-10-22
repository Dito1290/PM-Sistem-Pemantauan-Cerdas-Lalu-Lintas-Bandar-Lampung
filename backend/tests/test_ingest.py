"""Ingest supervisor: which cameras get a reader thread (FT-02 logic)."""
from __future__ import annotations

import threading

from citysight.extensions import db
from citysight.ingest import IngestSupervisor
from citysight.models import Camera
from citysight.pipeline import frame_queue
from citysight.timeutil import utcnow


class StubReader:
    instances: list["StubReader"] = []

    def __init__(self, camera_id, url, redis_client, settings, on_frame=None):
        self.camera_id, self.url = camera_id, url
        self.started = self.stopped = False
        StubReader.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def join(self, timeout=None):
        pass

    def is_alive(self):
        return self.started and not self.stopped


def running(sup):
    return {cid: r.url for cid, r in sup.readers.items()}


def test_supervisor_tracks_active_cameras(app, make_camera):
    StubReader.instances = []
    ids = [make_camera(name=f"C{i}") for i in range(4)]  # 4 active, bypassing API limit
    inactive = make_camera(name="off", status="inactive")
    sup = IngestSupervisor(app, reader_factory=StubReader, scheduler=lambda cid: None)

    sup.sync()
    assert sorted(sup.readers) == ids[:3]  # capped at MAX_ACTIVE_CAMERAS
    assert inactive not in sup.readers

    with app.app_context():
        db.session.get(Camera, ids[0]).status = "inactive"
        db.session.get(Camera, ids[1]).stream_url = "rtsp://cctv.example.test/new"
        db.session.get(Camera, ids[2]).deleted_at = utcnow()
        db.session.commit()
    old = dict(sup.readers)
    sup.sync()

    assert old[ids[0]].stopped and old[ids[2]].stopped and old[ids[1]].stopped
    assert running(sup) == {ids[1]: "rtsp://cctv.example.test/new", ids[3]: "rtsp://cctv.example.test/stream1"}


def test_supervisor_keeps_readers_when_db_unavailable(app, make_camera, monkeypatch):
    StubReader.instances = []
    make_camera()
    sup = IngestSupervisor(app, reader_factory=StubReader, scheduler=lambda cid: None)
    sup.sync()
    monkeypatch.setattr(sup, "desired_cameras", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    sup.sync()
    assert len(sup.readers) == 1 and not StubReader.instances[0].stopped


def test_dead_reader_is_restarted(app, make_camera):
    StubReader.instances = []
    camera_id = make_camera()
    sup = IngestSupervisor(app, reader_factory=StubReader, scheduler=lambda cid: None)
    sup.sync()
    sup.readers[camera_id].stopped = True  # thread died
    sup.sync()
    assert len(StubReader.instances) == 2 and sup.readers[camera_id] is StubReader.instances[1]


def test_schedule_detection_sends_one_task_per_camera(app, redis_client, monkeypatch):
    sent = []
    celery = app.extensions["celery"]
    monkeypatch.setattr(celery, "send_task", lambda name, **kw: sent.append((name, kw)))
    sup = IngestSupervisor(app)
    sup._schedule_detection(5)
    sup._schedule_detection(5)  # previous task still pending -> no duplicate
    assert len(sent) == 1
    assert sent[0][0] == "citysight.detect_latest_frame"
    assert sent[0][1]["queue"] == "detection" and sent[0][1]["args"] == [5]
    frame_queue.release_detection_slot(redis_client, 5)
    sup._schedule_detection(5)
    assert len(sent) == 2


def test_schedule_releases_slot_when_broker_fails(app, redis_client, monkeypatch):
    celery = app.extensions["celery"]

    def boom(*a, **k):
        raise ConnectionError("broker down")

    monkeypatch.setattr(celery, "send_task", boom)
    sup = IngestSupervisor(app)
    try:
        sup._schedule_detection(6)
    except ConnectionError:
        pass
    assert not redis_client.exists(frame_queue.pending_key(6))


def test_run_forever_stops_on_event(app):
    sup = IngestSupervisor(app, reader_factory=StubReader, scheduler=lambda cid: None)
    sup.stop_event.set()
    thread = threading.Thread(target=sup.run_forever)
    thread.start()
    thread.join(5)
    assert not thread.is_alive()
