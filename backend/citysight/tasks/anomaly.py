"""Celery task: periodic camera_offline check (scheduled by Celery Beat)."""
from __future__ import annotations

import logging
import time

from celery import shared_task
from flask import current_app

from ..extensions import db
from ..services import anomaly_service

log = logging.getLogger(__name__)
CHECK_TASK = "citysight.check_anomalies"
# After a restart no camera has delivered a frame yet; wait before calling them offline.
_STARTED = time.monotonic()


@shared_task(name=CHECK_TASK, ignore_result=True)
def check_anomalies() -> int:
    grace = current_app.config["ANOMALY_OFFLINE_MINUTES"] * 60
    try:
        events = anomaly_service.check_cameras(allow_start=time.monotonic() - _STARTED >= grace)
    except Exception:  # noqa: BLE001  (next run in a minute)
        db.session.rollback()
        log.exception("Anomaly check failed")
        return 0
    return len(events)
