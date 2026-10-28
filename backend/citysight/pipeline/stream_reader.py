"""One reader thread per camera: open the stream, sample a frame every
FRAME_INTERVAL_SECONDS, JPEG-encode it and push it to the Redis frame buffer.

Failure handling (proposal Bab 5.2.1 c, NFR-02):
* open fails / read fails / read times out -> release the capture, mark the
  camera ``reconnecting``, wait STREAM_RECONNECT_DELAY_SECONDS (5 s), retry.
* With the default 10 s open/read timeouts, a dead stream is detected within
  ~10 s and retried 5 s later, so a stream that comes back is reconnected in
  roughly 15-25 s, inside the 30 s target. This must still be measured (IT-01).
* Any unexpected exception is logged and treated like a disconnect; it never
  escapes the thread, so one bad camera cannot stop the others.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Protocol

import redis

from . import camera_state, frame_queue
from .sources import file_path, is_file_source, mask_url

log = logging.getLogger(__name__)

MAX_LAG_SECONDS = 2.0


class Capture(Protocol):
    def isOpened(self) -> bool: ...
    def grab(self) -> bool: ...
    def retrieve(self) -> tuple[bool, object]: ...
    def get(self, prop: int) -> float: ...
    def set(self, prop: int, value: float) -> bool: ...
    def release(self) -> None: ...


@dataclass(frozen=True)
class ReaderSettings:
    frame_interval: float = 0.2
    queue_max: int = 10
    jpeg_quality: int = 80
    reconnect_delay: float = 5.0
    open_timeout_ms: int = 10000
    read_timeout_ms: int = 10000
    loop_files: bool = True

    @classmethod
    def from_config(cls, config) -> "ReaderSettings":
        return cls(
            frame_interval=config["FRAME_INTERVAL_SECONDS"],
            queue_max=config["FRAME_QUEUE_MAX"],
            jpeg_quality=config["JPEG_QUALITY"],
            reconnect_delay=config["STREAM_RECONNECT_DELAY_SECONDS"],
            open_timeout_ms=config["STREAM_OPEN_TIMEOUT_MS"],
            read_timeout_ms=config["STREAM_READ_TIMEOUT_MS"],
        )


def open_capture(url: str, settings: ReaderSettings) -> Capture:
    import cv2

    if is_file_source(url):
        return cv2.VideoCapture(file_path(url))
    params = [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, settings.open_timeout_ms,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC, settings.read_timeout_ms,
    ]
    return cv2.VideoCapture(url, cv2.CAP_FFMPEG, params)


def encode_jpeg(frame, quality: int) -> bytes:
    import cv2

    ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return buffer.tobytes()


class StreamReader(threading.Thread):
    def __init__(
        self,
        camera_id: int,
        url: str,
        redis_client: redis.Redis,
        settings: ReaderSettings,
        on_frame: Callable[[int], None] | None = None,
        capture_factory: Callable[[str, ReaderSettings], Capture] = open_capture,
        encoder: Callable[[object, int], bytes] = encode_jpeg,
    ):
        super().__init__(name=f"camera-{camera_id}", daemon=True)
        self.camera_id = camera_id
        self.url = url
        self.redis = redis_client
        self.settings = settings
        self.on_frame = on_frame
        self.capture_factory = capture_factory
        self.encoder = encoder
        self.stop_event = threading.Event()
        self.is_file = is_file_source(url)

    def stop(self) -> None:
        self.stop_event.set()

    # -- main loop ---------------------------------------------------------
    def run(self) -> None:
        log.info("Camera %s: reader started for %s", self.camera_id, mask_url(self.url))
        first_attempt = True
        while not self.stop_event.is_set():
            camera_state.set_state(self.redis, self.camera_id, "connecting" if first_attempt else "reconnecting")
            error = self._run_session()
            if self.stop_event.is_set():
                break
            first_attempt = False
            camera_state.set_state(self.redis, self.camera_id, "reconnecting", error=error)
            camera_state.touch(self.redis, self.camera_id, reconnect_count=1)
            log.warning(
                "Camera %s: %s; reconnecting in %.0fs", self.camera_id, error, self.settings.reconnect_delay
            )
            self.stop_event.wait(self.settings.reconnect_delay)
        camera_state.set_state(self.redis, self.camera_id, "stopped")
        log.info("Camera %s: reader stopped", self.camera_id)

    def _run_session(self) -> str:
        """Read until the stream fails; return the failure reason."""
        capture = None
        try:
            capture = self.capture_factory(self.url, self.settings)
            if capture is None or not capture.isOpened():
                return "stream tidak dapat dibuka"
            camera_state.set_state(self.redis, self.camera_id, "online", last_connected_at=time.time())
            log.info("Camera %s: stream opened", self.camera_id)
            return self._read_loop(capture)
        except Exception as exc:  # noqa: BLE001 - must never kill the thread
            log.exception("Camera %s: unexpected reader error", self.camera_id)
            return f"error: {exc.__class__.__name__}"
        finally:
            if capture is not None:
                try:
                    capture.release()
                except Exception:  # noqa: BLE001
                    pass

    def _read_loop(self, capture: Capture) -> str:
        interval = self.settings.frame_interval
        period = self._frame_period(capture)
        next_sample = time.monotonic()
        play_at = None
        while not self.stop_event.is_set():
            if not capture.grab():
                if self.is_file and self.settings.loop_files and self._rewind(capture):
                    continue
                return "frame tidak dapat dibaca (stream terputus)"
            # Release frames at the video's native speed, like a live player.
            # HLS delivers a whole segment (several seconds) in one burst; sampling
            # the burst by wall clock keeps only ~2 frames per segment (measured
            # 0.4 fps instead of 5). Local test videos are paced the same way.
            # If reading falls more than MAX_LAG_SECONDS behind, resync instead
            # of trying to catch up.
            now = time.monotonic()
            if play_at is None or now - play_at > MAX_LAG_SECONDS:
                play_at = now
            else:
                play_at += period
                if play_at > now:
                    self.stop_event.wait(play_at - now)
            now = time.monotonic()
            if now < next_sample:
                continue
            next_sample = max(next_sample + interval, now)
            ok, frame = capture.retrieve()
            if not ok or frame is None:
                return "frame tidak dapat didekode"
            self._publish(frame)
        return "stopped"

    def _publish(self, frame) -> None:
        captured_at = time.time()
        jpeg = self.encoder(frame, self.settings.jpeg_quality)
        try:
            evicted = frame_queue.push_frame(self.redis, self.camera_id, captured_at, jpeg, self.settings.queue_max)
        except redis.RedisError as exc:
            # Redis down: drop the frame but keep the stream open.
            log.warning("Camera %s: cannot queue frame: %s", self.camera_id, exc)
            return
        camera_state.touch(self.redis, self.camera_id, frames_captured=1, frames_evicted=evicted)
        try:
            self.redis.hset(camera_state.state_key(self.camera_id), "last_frame_at", captured_at)
        except redis.RedisError:
            pass
        if self.on_frame is not None:
            try:
                self.on_frame(self.camera_id)
            except Exception:  # noqa: BLE001 - broker issues must not stop capture
                log.exception("Camera %s: cannot schedule detection", self.camera_id)

    @staticmethod
    def _frame_period(capture: Capture) -> float:
        import cv2

        fps = capture.get(cv2.CAP_PROP_FPS) or 0
        return 1.0 / fps if 0 < fps <= 120 else 1.0 / 25

    @staticmethod
    def _rewind(capture: Capture) -> bool:
        import cv2

        return bool(capture.set(cv2.CAP_PROP_POS_FRAMES, 0)) and capture.grab()
