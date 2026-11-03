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
        detector = get_detector(app.config)
        # The first inference is slow (CUDA setup took ~30 s on the RTX 3050),
        # long enough for the first frames to go stale; run it now.
        import numpy as np

        detector.detect(np.zeros((app.config["YOLO_IMGSZ"], app.config["YOLO_IMGSZ"], 3), np.uint8))
    except (ModelUnavailable, ModelConfigError) as exc:
        # Keep the worker alive (stats tasks still work); detection tasks will log the error.
        log.error("YOLO model not loaded: %s", exc)
