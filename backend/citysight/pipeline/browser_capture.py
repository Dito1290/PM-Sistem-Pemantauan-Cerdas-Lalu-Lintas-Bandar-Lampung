"""Seribu Wajah cameras read through the public web player.

Direct requests to the Seribu Wajah streams answer 401, but the public page
https://seribuwajah.bandarlampungkota.go.id/list plays every camera to
anonymous visitors. This capture drives a headless browser (Playwright)
through that page like a visitor: it searches the camera by name, opens its
live monitor and copies frames from the <video> element at full resolution
(1920x1080 measured on 2026-11-02).

A camera's stream_url is the list page plus the Seribu Wajah camera id, e.g.
``https://seribuwajah.bandarlampungkota.go.id/list?cctv=313``. The ids come
from the camera list the page loads (``api-newseribuwajah.../cctvs``).

Two modes, chosen from FRAME_INTERVAL_SECONDS:

* continuous (interval < ONE_SHOT_MIN_INTERVAL): the monitor stays open and
  frames are copied as the video plays.
* one shot (interval >= ONE_SHOT_MIN_INTERVAL, e.g. one frame per minute):
  the monitor is opened only to take a frame and closed again, so the video
  does not play (and use CPU) between samples. Opening takes 6-13 s.

It implements the ``Capture`` protocol of stream_reader, so StreamReader's
pacing, sampling and reconnect logic apply unchanged. Playwright's sync API
must stay in the thread that started it, so every reader thread owns its own
browser.
"""
from __future__ import annotations

import base64
import logging
import re
import time
from urllib.parse import parse_qs, urlsplit, urlunsplit

log = logging.getLogger(__name__)

SERIBU_WAJAH_HOST = "seribuwajah.bandarlampungkota.go.id"
LIST_PATH = "/list"
# The page, its camera list and the first video frame together take several
# seconds on this site, longer than STREAM_OPEN_TIMEOUT_MS is meant for.
PAGE_TIMEOUT_MS = 30000
POLL_SECONDS = 0.05
JPEG_QUALITY = 0.95  # re-encoded by StreamReader with JPEG_QUALITY
ONE_SHOT_MIN_INTERVAL = 30.0
# One-shot mode: StreamReader calls grab() at this rate and samples by wall
# clock, so the slow retrieve() does not shift the next sample.
ONE_SHOT_TICK_FPS = 1.0

VIDEO_PLAYING = "v => v.readyState >= 2 && v.videoWidth > 0"
VIDEO_POSITION = "v => v.ended ? -1 : v.currentTime"
VIDEO_FRAME = """(v, quality) => {
  const canvas = document.createElement('canvas');
  canvas.width = v.videoWidth;
  canvas.height = v.videoHeight;
  canvas.getContext('2d').drawImage(v, 0, 0);
  return canvas.toDataURL('image/jpeg', quality);
}"""


def seribu_wajah_camera(url: str) -> int | None:
    """Return the Seribu Wajah camera id of a ``/list?cctv=<id>`` URL."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if (parts.hostname or "").lower() != SERIBU_WAJAH_HOST:
        return None
    values = parse_qs(parts.query).get("cctv", [])
    return int(values[0]) if values and values[0].isdigit() else None


def is_seribu_wajah_page(url: str) -> bool:
    return seribu_wajah_camera(url) is not None


class BrowserCapture:
    def __init__(self, url: str, *, frame_interval: float, timeout: float, channel: str = ""):
        from playwright.sync_api import sync_playwright

        self.url = url
        self.cctv_id = seribu_wajah_camera(url)
        self.frame_interval = frame_interval
        self.timeout = timeout  # for the next video frame
        self.one_shot = frame_interval >= ONE_SHOT_MIN_INTERVAL
        self.name = None
        self.browser = None
        self.page = None
        self.video = None
        self.position = None
        self.pending = None  # one-shot: frame taken while opening, returned by the first retrieve()
        self.playwright = sync_playwright().start()
        try:
            # channel "chrome" uses the installed Google Chrome; empty uses
            # Playwright's Chromium (`playwright install chromium`).
            self.browser = self.playwright.chromium.launch(headless=True, channel=channel or None)
            self._open_monitor()
            if self.one_shot:
                self.pending = self._copy_frame()
                self._close_page()
                if self.pending is None:
                    raise RuntimeError("first frame is empty")
            log.info("Seribu Wajah camera %s: monitor opened (%s)%s", self.cctv_id, self.name,
                     ", one frame per sample" if self.one_shot else "")
        except Exception as exc:  # noqa: BLE001 - isOpened() stays False; StreamReader retries
            log.warning("Seribu Wajah camera %s: cannot open the monitor: %s",
                        self.cctv_id, str(exc).splitlines()[0])
            self.release()

    # -- Capture protocol --------------------------------------------------
    def isOpened(self) -> bool:
        return self.browser is not None

    def grab(self) -> bool:
        """Wait until the video shows a new frame; False if it stalls.

        One-shot mode has no video between samples; the frame is taken in
        retrieve(), which StreamReader calls only when it samples.
        """
        from playwright.sync_api import Error

        if self.one_shot:
            return self.browser is not None
        if self.video is None:
            return False
        deadline = time.monotonic() + self.timeout
        try:
            while True:
                position = self.video.evaluate(VIDEO_POSITION)
                if position >= 0 and position != self.position:
                    self.position = position
                    return True
                if time.monotonic() > deadline:
                    return False
                time.sleep(POLL_SECONDS)
        except Error:
            return False

    def retrieve(self):
        if self.browser is None:
            return False, None
        if not self.one_shot:
            frame = self._copy_frame()
            return frame is not None, frame
        frame, self.pending = self.pending, None
        if frame is None:
            try:
                self._open_monitor()
                frame = self._copy_frame()
            except Exception as exc:  # noqa: BLE001 - StreamReader reconnects
                log.warning("Seribu Wajah camera %s: cannot take a frame: %s",
                            self.cctv_id, str(exc).splitlines()[0])
                frame = None
            finally:
                self._close_page()
        return frame is not None, frame

    def get(self, prop: int) -> float:
        import cv2

        if prop != cv2.CAP_PROP_FPS:
            return 0.0
        # StreamReader calls grab() once per frame period. The browser plays
        # the video by itself, so one grab per sample is enough.
        return ONE_SHOT_TICK_FPS if self.one_shot else 1.0 / self.frame_interval

    def set(self, prop: int, value: float) -> bool:
        return False  # live: no seeking

    def release(self) -> None:
        self.video = None
        self.page = None
        for close in (self.browser and self.browser.close, self.playwright.stop):
            if close is None:
                continue
            try:
                close()
            except Exception:  # noqa: BLE001
                pass
        self.browser = None

    # -- internals ---------------------------------------------------------
    def _open_monitor(self) -> None:
        page = self.browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_default_timeout(PAGE_TIMEOUT_MS)
        self.page = page
        parts = urlsplit(self.url)
        list_url = urlunsplit((parts.scheme, parts.netloc, LIST_PATH, "", ""))
        with page.expect_response(lambda r: r.url.endswith("/cctvs")) as listing:
            page.goto(list_url, wait_until="domcontentloaded")
        if self.name is None:
            cameras = listing.value.json()
            self.name = next((c["name"] for c in cameras if c.get("id") == self.cctv_id), None)
            if self.name is None:
                raise LookupError(f"id {self.cctv_id} is not in the Seribu Wajah camera list")
        page.get_by_placeholder(re.compile("Cari nama kamera")).fill(self.name)
        page.get_by_text(self.name, exact=True).first.click()
        # List tiles are images; the only <video> is the live monitor.
        self.video = page.locator("video").first
        page.wait_for_function(f"() => {{ const v = document.querySelector('video'); return v && ({VIDEO_PLAYING})(v); }}")

    def _copy_frame(self):
        import cv2
        import numpy as np
        from playwright.sync_api import Error

        try:
            data_url = self.video.evaluate(VIDEO_FRAME, JPEG_QUALITY)
        except Error:
            return None
        jpeg = base64.b64decode(data_url.split(",", 1)[1])
        if not jpeg:  # "data:," while the player reloads (video 0x0)
            return None
        return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)

    def _close_page(self) -> None:
        self.video = None
        if self.page is not None:
            try:
                self.page.close()
            except Exception:  # noqa: BLE001
                pass
            self.page = None
