"""Ingest service: keeps one StreamReader thread per active camera.

Run with ``flask --app wsgi ingest run``. Every CAMERA_SYNC_INTERVAL_SECONDS
the camera table is re-read: readers are started for newly activated cameras,
stopped for deactivated/deleted ones, and restarted when the URL changes. At
most MAX_ACTIVE_CAMERAS readers run. DB outages keep existing readers going.
"""
from __future__ import annotations

import logging
import signal
import threading

from flask import Flask
from sqlalchemy import select

from .extensions import db
from .models import Camera
from .pipeline import frame_queue
from .pipeline.stream_reader import ReaderSettings, StreamReader
from .redis_client import get_redis

log = logging.getLogger(__name__)


class IngestSupervisor:
    def __init__(self, app: Flask, reader_factory=StreamReader, scheduler=None):
        self.app = app
        self.config = app.config
        self.redis = get_redis(app.config["REDIS_URL"])
        self.settings = ReaderSettings.from_config(app.config)
        self.reader_factory = reader_factory
        self.scheduler = scheduler or self._schedule_detection
        self.readers: dict[int, StreamReader] = {}
        self.stop_event = threading.Event()

    def _schedule_detection(self, camera_id: int) -> None:
        if frame_queue.claim_detection_slot(self.redis, camera_id):
            celery = self.app.extensions["celery"]
            try:
                # expires: a queued task older than this is useless (frame is stale).
                celery.send_task("citysight.detect_latest_frame", args=[camera_id],
                                 queue="detection", expires=10)
            except Exception:
                frame_queue.release_detection_slot(self.redis, camera_id)
                raise

    def desired_cameras(self) -> dict[int, str]:
        with self.app.app_context():
            rows = db.session.execute(
                select(Camera.id, Camera.stream_url)
                .where(Camera.deleted_at.is_(None), Camera.status == "active")
                .order_by(Camera.id)
                .limit(self.config["MAX_ACTIVE_CAMERAS"])
            ).all()
            db.session.remove()
        return {row.id: row.stream_url for row in rows}

    def sync(self) -> None:
        try:
            desired = self.desired_cameras()
        except Exception:  # noqa: BLE001
            log.exception("Cannot read cameras; keeping %d reader(s) running", len(self.readers))
            return
        for camera_id, reader in list(self.readers.items()):
            if desired.get(camera_id) != reader.url or not reader.is_alive():
                log.info("Stopping reader for camera %s", camera_id)
                reader.stop()
                reader.join(timeout=15)
                del self.readers[camera_id]
        for camera_id, url in desired.items():
            if camera_id not in self.readers:
                reader = self.reader_factory(camera_id, url, self.redis, self.settings, on_frame=self.scheduler)
                reader.start()
                self.readers[camera_id] = reader

    def run_forever(self) -> None:
        log.info("Ingest supervisor started (max %d cameras)", self.config["MAX_ACTIVE_CAMERAS"])
        while not self.stop_event.is_set():
            self.sync()
            self.stop_event.wait(self.config["CAMERA_SYNC_INTERVAL_SECONDS"])
        self.shutdown()

    def shutdown(self) -> None:
        for reader in self.readers.values():
            reader.stop()
        for reader in self.readers.values():
            reader.join(timeout=15)
        self.readers.clear()
        log.info("Ingest supervisor stopped")

    def install_signal_handlers(self) -> None:
        def _stop(signum, _frame):
            log.info("Received signal %s, stopping", signum)
            self.stop_event.set()

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
