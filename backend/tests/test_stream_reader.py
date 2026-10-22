"""Stream acquisition, failure handling and reconnect (FT-01, part of IT-01).

The first group uses scripted fake captures. The ``opencv`` group drives the
real OpenCV/FFmpeg code path against locally generated video files and an
unreachable RTSP address. None of these is a test against real CCTV.
"""
from __future__ import annotations

import time

import cv2
import numpy as np
import pytest

from citysight.pipeline import camera_state, frame_queue
from citysight.pipeline.stream_reader import ReaderSettings, StreamReader

from .fakes import FakeCapture, ScriptedFactory

FAST = ReaderSettings(frame_interval=0.01, queue_max=10, reconnect_delay=0.1)


def wait_for(predicate, timeout=5.0, step=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return False


def state(redis_client, camera_id):
    return camera_state.read_states(redis_client, [camera_id])[camera_id]


def make_reader(redis_client, factory, settings=FAST, on_frame=None, url="rtsp://cctv.example.test/x"):
    return StreamReader(1, url, redis_client, settings, on_frame=on_frame,
                        capture_factory=factory, encoder=lambda frame, q: b"jpeg")


def test_open_failure_marks_reconnecting_and_retries(redis_client):
    factory = ScriptedFactory([])  # never opens
    reader = make_reader(redis_client, factory)
    reader.start()
    try:
        assert wait_for(lambda: factory.attempts >= 3)
        s = state(redis_client, 1)
        assert s["state"] in {"reconnecting", "connecting"}
        assert s["last_error"] == "stream tidak dapat dibuka"
        assert s["reconnect_count"] >= 2
    finally:
        reader.stop()
        reader.join(2)
    assert not reader.is_alive()
    assert state(redis_client, 1)["state"] == "stopped"


def test_reconnects_after_stream_drop_and_resumes(redis_client):
    first, second = FakeCapture(frames=3), FakeCapture(frames=None)
    factory = ScriptedFactory([FakeCapture(opened=False), first, second])
    scheduled = []
    reader = make_reader(redis_client, factory, on_frame=scheduled.append)
    reader.start()
    try:
        assert wait_for(lambda: factory.attempts >= 3 and len(scheduled) > 10)
        assert state(redis_client, 1)["state"] == "online"
        assert first.released  # dropped capture is released before reconnecting
        assert state(redis_client, 1)["reconnect_count"] == 2
        assert frame_queue.queue_length(redis_client, 1) <= 10
    finally:
        reader.stop()
        reader.join(2)


def test_reconnect_waits_configured_delay(redis_client):
    settings = ReaderSettings(frame_interval=0.01, reconnect_delay=0.5)
    factory = ScriptedFactory([FakeCapture(opened=False), FakeCapture(frames=None)])
    reader = make_reader(redis_client, factory, settings=settings)
    started = time.monotonic()
    reader.start()
    try:
        assert wait_for(lambda: state(redis_client, 1)["state"] == "online", timeout=3)
        elapsed = time.monotonic() - started
        assert 0.45 <= elapsed < 1.5
    finally:
        reader.stop()
        reader.join(2)


def test_exception_in_capture_does_not_kill_thread(redis_client):
    calls = {"n": 0}

    def factory(url, settings):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return FakeCapture(frames=None)

    reader = make_reader(redis_client, factory)
    reader.start()
    try:
        assert wait_for(lambda: state(redis_client, 1)["state"] == "online")
        assert reader.is_alive()
    finally:
        reader.stop()
        reader.join(2)


def test_scheduler_failure_does_not_stop_capture(redis_client):
    def broken(_camera_id):
        raise ConnectionError("broker down")

    reader = make_reader(redis_client, ScriptedFactory([FakeCapture(frames=None)]), on_frame=broken)
    reader.start()
    try:
        assert wait_for(lambda: state(redis_client, 1)["frames_captured"] >= 5)
        assert reader.is_alive()
    finally:
        reader.stop()
        reader.join(2)


# --- real OpenCV path ---------------------------------------------------------------

def write_video(path, seconds=2, fps=25):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (160, 120))
    assert writer.isOpened()
    for i in range(seconds * fps):
        frame = np.full((120, 160, 3), (i * 5) % 255, np.uint8)
        cv2.putText(frame, str(i), (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        writer.write(frame)
    writer.release()


@pytest.mark.opencv
def test_opencv_file_source_sampled_at_five_fps(tmp_path, redis_client):
    video = tmp_path / "traffic.avi"
    write_video(video)
    settings = ReaderSettings(frame_interval=0.2, queue_max=10, jpeg_quality=80, reconnect_delay=5)
    reader = StreamReader(7, str(video), redis_client, settings)
    reader.start()
    time.sleep(3.0)
    reader.stop()
    reader.join(3)
    captured = state(redis_client, 7)["frames_captured"]
    # 3 s at 0.2 s interval ~= 15 frames (+1 for the first frame at t=0).
    assert 13 <= captured <= 17, captured
    assert frame_queue.queue_length(redis_client, 7) == 10
    newest = frame_queue.take_latest(redis_client, 7)
    image = cv2.imdecode(np.frombuffer(newest.jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert image.shape == (120, 160, 3)


@pytest.mark.opencv
def test_opencv_unreachable_rtsp_reports_error(redis_client):
    settings = ReaderSettings(reconnect_delay=0.2, open_timeout_ms=2000, read_timeout_ms=2000)
    reader = StreamReader(8, "rtsp://127.0.0.1:9/none", redis_client, settings)
    reader.start()
    try:
        assert wait_for(lambda: state(redis_client, 8).get("reconnect_count", 0) >= 1, timeout=10)
        assert state(redis_client, 8)["last_error"] == "stream tidak dapat dibuka"
    finally:
        reader.stop()
        reader.join(5)


@pytest.mark.opencv
def test_opencv_reconnects_when_source_becomes_available(tmp_path, redis_client):
    video = tmp_path / "later.avi"
    settings = ReaderSettings(frame_interval=0.2, reconnect_delay=1.0)
    reader = StreamReader(9, str(video), redis_client, settings)
    reader.start()
    try:
        assert wait_for(lambda: state(redis_client, 9).get("reconnect_count", 0) >= 1, timeout=5)
        write_video(video, seconds=1)
        restored_at = time.monotonic()
        assert wait_for(lambda: state(redis_client, 9)["state"] == "online", timeout=5)
        assert time.monotonic() - restored_at <= 1.5  # <= one reconnect delay (+ margin)
        assert wait_for(lambda: state(redis_client, 9)["frames_captured"] >= 2, timeout=5)
    finally:
        reader.stop()
        reader.join(3)
