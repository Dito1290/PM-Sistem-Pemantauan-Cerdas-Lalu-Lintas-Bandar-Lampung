"""Newest detected frame per camera, for live views (Redis hash ``camera:live:{id}``).

The worker overwrites it after every detection with the JPEG and the boxes
it counted, so a viewer can draw exactly what the system counted without
running YOLO again. It holds one frame per camera and expires when the
pipeline stops.
"""
from __future__ import annotations

import json
import logging

import redis

log = logging.getLogger(__name__)
TTL_SECONDS = 30


def live_key(camera_id: int) -> str:
    return f"camera:live:{camera_id}"


def publish(client: redis.Redis, camera_id: int, jpeg: bytes, event: dict, boxes: list[dict]) -> None:
    """``event`` is the realtime detection event (counts, timestamp, stored)."""
    meta = {**event, "boxes": boxes}
    try:
        pipe = client.pipeline(transaction=True)
        pipe.hset(live_key(camera_id), mapping={"meta": json.dumps(meta), "jpeg": jpeg})
        pipe.expire(live_key(camera_id), TTL_SECONDS)
        pipe.execute()
    except redis.RedisError as exc:  # the live view is optional; detection goes on
        log.warning("Cannot store live frame for camera %s: %s", camera_id, exc)


def read(client: redis.Redis, camera_id: int) -> tuple[dict, bytes] | None:
    meta, jpeg = client.hmget(live_key(camera_id), ["meta", "jpeg"])
    if not meta or not jpeg:
        return None
    return json.loads(meta), jpeg
