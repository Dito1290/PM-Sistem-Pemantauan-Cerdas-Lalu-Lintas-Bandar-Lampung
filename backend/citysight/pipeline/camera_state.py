"""Runtime camera connection state, stored in Redis hash ``camera:state:{id}``.

States: connecting, online, reconnecting, stopped. ``offline`` is derived when
the ingest service has not refreshed the hash recently (service not running).
"""
from __future__ import annotations

import logging
import time

import redis

log = logging.getLogger(__name__)
STALE_AFTER_SECONDS = 30
COUNTERS = ("frames_captured", "frames_evicted", "frames_discarded", "frames_stale", "reconnect_count")


def state_key(camera_id: int) -> str:
    return f"camera:state:{camera_id}"


def latest_key(camera_id: int) -> str:
    return f"camera:latest:{camera_id}"


def set_state(client: redis.Redis, camera_id: int, state: str, error: str | None = None, **extra) -> None:
    mapping: dict[str, str | float] = {"state": state, "updated_at": time.time()}
    if error is not None:
        mapping["last_error"] = error[:300]
        mapping["last_error_at"] = time.time()
    mapping.update({k: v for k, v in extra.items() if v is not None})
    try:
        client.hset(state_key(camera_id), mapping=mapping)
    except redis.RedisError as exc:  # state is advisory; never kill the stream for it
        log.warning("Cannot write state for camera %s: %s", camera_id, exc)


def touch(client: redis.Redis, camera_id: int, **counters: int) -> None:
    try:
        pipe = client.pipeline(transaction=False)
        pipe.hset(state_key(camera_id), "updated_at", time.time())
        for name, amount in counters.items():
            if amount:
                pipe.hincrby(state_key(camera_id), name, amount)
        pipe.execute()
    except redis.RedisError as exc:
        log.warning("Cannot update counters for camera %s: %s", camera_id, exc)


def read_states(client: redis.Redis, camera_ids: list[int]) -> dict[int, dict]:
    """Return a JSON-friendly state per camera; ``unknown`` if Redis is down."""
    if not camera_ids:
        return {}

    def empty(state: str) -> dict:
        return {
            "state": state, "last_frame_at": None, "last_connected_at": None, "last_error": None,
            "last_error_at": None, "last_inference_error": None, **dict.fromkeys(COUNTERS, 0),
        }

    try:
        pipe = client.pipeline(transaction=False)
        for camera_id in camera_ids:
            pipe.hgetall(state_key(camera_id))
        raw = pipe.execute()
    except redis.RedisError as exc:
        log.warning("Cannot read camera states: %s", exc)
        return {cid: empty("unknown") for cid in camera_ids}

    now = time.time()
    result = {}
    for camera_id, values in zip(camera_ids, raw):
        data = {k.decode(): v.decode() for k, v in values.items()}
        if not data:
            result[camera_id] = empty("offline")
            continue
        updated = float(data.get("updated_at", 0))
        state = data.get("state", "unknown")
        if state != "stopped" and now - updated > STALE_AFTER_SECONDS:
            state = "offline"
        result[camera_id] = {
            "state": state,
            "last_frame_at": _ts(data.get("last_frame_at")),
            "last_connected_at": _ts(data.get("last_connected_at")),
            "last_error": data.get("last_error"),
            "last_error_at": _ts(data.get("last_error_at")),
            "last_inference_error": data.get("last_inference_error") or None,
            **{name: int(data.get(name, 0)) for name in COUNTERS},
        }
    return result


def _ts(value: str | None):
    if not value:
        return None
    from datetime import datetime, timezone

    from ..timeutil import isoformat

    return isoformat(datetime.fromtimestamp(float(value), tz=timezone.utc))
