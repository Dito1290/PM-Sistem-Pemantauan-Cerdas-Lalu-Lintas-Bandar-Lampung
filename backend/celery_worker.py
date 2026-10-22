"""Celery entry point.

    celery -A celery_worker.celery worker -Q detection,stats --concurrency 3 -l info
    celery -A celery_worker.celery beat -l info
"""
import logging

from celery.signals import worker_process_init

from citysight import create_app
from citysight.pipeline.detector import ModelConfigError, ModelUnavailable, get_detector

app = create_app()
celery = app.extensions["celery"]
log = logging.getLogger("citysight.worker")


@worker_process_init.connect
def _preload_model(**_kwargs):
    """Load YOLO once per worker process instead of on the first frame."""
    try:
        get_detector(app.config)
    except (ModelUnavailable, ModelConfigError) as exc:
        # Keep the worker alive (stats tasks still work); detection tasks will log the error.
        log.error("YOLO model not loaded: %s", exc)
