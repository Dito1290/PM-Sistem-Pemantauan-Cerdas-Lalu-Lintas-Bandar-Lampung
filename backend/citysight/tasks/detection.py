"""Celery task: count vehicles in the newest buffered frame of one camera."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import redis
from celery import shared_task
from flask import current_app
from sqlalchemy.exc import IntegrityError, OperationalError

from ..extensions import db
from ..pipeline import camera_state, frame_queue
from ..pipeline.detector import ModelConfigError, ModelUnavailable, get_detector
from ..redis_client import get_redis
from ..services.detection_service import save_detection
from ..services.realtime import publish_detection
from ..services.serializers import detection_to_dict

log = logging.getLogger(__name__)
DETECT_TASK = "citysight.detect_latest_frame"
_MODEL_ERROR_LOG_INTERVAL = 60.0
_last_model_error_log = 0.0


def decode_jpeg(jpeg: bytes):
    import cv2
    import numpy as np

    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Cannot decode JPEG frame")
    return image


@shared_task(name=DETECT_TASK, ignore_result=True)
def detect_latest_frame(camera_id: int) -> dict | None:
    """Process at most one frame; failures are logged and never re-raised so a
    bad frame or a missing model cannot crash the worker or the API."""
    config = current_app.config
    client = get_redis(config["REDIS_URL"])
    try:
        frame = frame_queue.take_latest(client, camera_id)
        if frame is None:
            return None
        if frame.discarded:
            camera_state.touch(client, camera_id, frames_discarded=frame.discarded)
        if frame.age > config["FRAME_MAX_AGE_SECONDS"]:
            camera_state.touch(client, camera_id, frames_stale=1)
            log.warning("Camera %s: dropped stale frame (%.1fs old)", camera_id, frame.age)
            return None

        counts = get_detector(config).detect(decode_jpeg(frame.jpeg))
        captured_at = datetime.fromtimestamp(frame.captured_at, tz=timezone.utc)
        detection = save_detection(camera_id, captured_at, counts)
        if detection is None:  # same frame already stored (retry)
            return None
        event = detection_to_dict(detection)
        publish_detection(client, event)
        try:
            client.hset(camera_state.state_key(camera_id), mapping={"last_inference_error": ""})
        except redis.RedisError:
            pass
        return event
    except (ModelUnavailable, ModelConfigError) as exc:
        global _last_model_error_log
        if time.monotonic() - _last_model_error_log >= _MODEL_ERROR_LOG_INTERVAL:
            _last_model_error_log = time.monotonic()
            log.error("Camera %s: model not usable (frames are dropped until fixed): %s", camera_id, exc)
        _record_inference_error(client, camera_id, str(exc))
    except IntegrityError as exc:
        db.session.rollback()
        log.warning("Camera %s: detection rejected by DB (camera removed?): %s", camera_id, exc.orig)
    except OperationalError:
        db.session.rollback()
        log.error("Camera %s: database unavailable, detection dropped", camera_id)
        _record_inference_error(client, camera_id, "database unavailable")
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        log.exception("Camera %s: detection failed", camera_id)
        _record_inference_error(client, camera_id, exc.__class__.__name__)
    finally:
        try:
            frame_queue.release_detection_slot(client, camera_id)
        except redis.RedisError:
            pass
    return None


def _record_inference_error(client, camera_id: int, message: str) -> None:
    try:
        client.hset(camera_state.state_key(camera_id), mapping={"last_inference_error": message[:300]})
    except redis.RedisError:
        pass
