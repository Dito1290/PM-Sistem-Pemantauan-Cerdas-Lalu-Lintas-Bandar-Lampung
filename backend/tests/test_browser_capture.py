"""Routing of Seribu Wajah cameras to the browser capture.

Opening the real web player needs a browser and the internet, so it is not
tested here; it was checked by hand against the live site.
"""
from __future__ import annotations

import cv2
import numpy as np

from citysight.pipeline import stream_reader
from citysight.pipeline.browser_capture import (
    ONE_SHOT_TICK_FPS,
    BrowserCapture,
    is_seribu_wajah_page,
    seribu_wajah_camera,
)
from citysight.pipeline.stream_reader import ReaderSettings, open_capture


def test_camera_id_is_read_from_the_list_page_url():
    assert seribu_wajah_camera("https://seribuwajah.bandarlampungkota.go.id/list?cctv=313") == 313
    assert seribu_wajah_camera("https://SERIBUWAJAH.bandarlampungkota.go.id/list?cctv=31&x=1") == 31


def test_other_urls_are_not_seribu_wajah_pages():
    assert not is_seribu_wajah_page("https://seribuwajah.bandarlampungkota.go.id/list")
    assert not is_seribu_wajah_page("https://seribuwajah.bandarlampungkota.go.id/list?cctv=abc")
    assert not is_seribu_wajah_page("https://stream-newseribuwajah.bandarlampungkota.go.id/cctv_313/index.m3u8")
    assert not is_seribu_wajah_page("rtsp://10.0.0.5/stream?cctv=1")
    assert not is_seribu_wajah_page(r"C:\videos\malioboro.mp4")


def test_open_capture_uses_the_browser_for_seribu_wajah(monkeypatch):
    opened = []
    monkeypatch.setattr(stream_reader, "BrowserCapture", lambda url, **kw: opened.append((url, kw)) or "browser")
    settings = ReaderSettings(frame_interval=0.2, read_timeout_ms=10000, browser_channel="chrome")

    url = "https://seribuwajah.bandarlampungkota.go.id/list?cctv=313"
    assert open_capture(url, settings) == "browser"
    assert opened == [(url, {"frame_interval": 0.2, "timeout": 10.0, "channel": "chrome"})]


def one_shot_capture(pending):
    """A one-shot BrowserCapture without a browser: only the state matters here."""
    capture = BrowserCapture.__new__(BrowserCapture)
    capture.one_shot, capture.browser, capture.frame_interval = True, object(), 60.0
    capture.pending, capture.video, capture.page = pending, None, None
    return capture


def test_one_shot_mode_returns_the_frame_taken_while_opening_first():
    frame = np.zeros((2, 2, 3), np.uint8)
    capture = one_shot_capture(pending=frame)
    assert capture.grab()  # no video to wait for between samples
    ok, got = capture.retrieve()
    assert ok and got is frame and capture.pending is None


def test_one_shot_mode_ticks_once_per_second_so_samples_follow_the_wall_clock():
    assert one_shot_capture(pending=None).get(cv2.CAP_PROP_FPS) == ONE_SHOT_TICK_FPS
