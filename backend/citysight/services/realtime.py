"""Realtime detection events over Redis pub/sub, served to browsers as SSE.

Event payload (also the shape of each SSE ``data:`` line):
    {"camera_id", "timestamp", "car_count", "motorcycle_count", "bus_count",
     "truck_count", "total_vehicle", "stored"}
``stored`` is false (and ``id`` null) for frames shown live but not saved,
see DETECTION_SAVE_INTERVAL_SECONDS.

Anomaly events (SSE ``event: anomaly``) carry ``{"change": "started"|"ended", ...}``
plus the fields of GET /api/anomalies.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator

import redis

log = logging.getLogger(__name__)
CHANNEL = "citysight:detections"
ANOMALY_CHANNEL = "citysight:anomalies"
HEARTBEAT_SECONDS = 15


def publish_detection(client: redis.Redis, event: dict) -> None:
    _publish(client, CHANNEL, event)


def publish_anomaly(client: redis.Redis, event: dict) -> None:
    _publish(client, ANOMALY_CHANNEL, event)


def _publish(client: redis.Redis, channel: str, event: dict) -> None:
    try:
        client.publish(channel, json.dumps(event))
    except redis.RedisError as exc:  # dashboard can still poll the REST API
        log.warning("Cannot publish realtime event: %s", exc)


def sse_format(event: str, data: dict | None = None, event_id: str | None = None) -> str:
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data or {})}")
    return "\n".join(lines) + "\n\n"


def stream_events(client: redis.Redis, camera_ids: set[int] | None, max_seconds: float | None = None) -> Iterator[str]:
    """Yield SSE frames until the client disconnects (GeneratorExit)."""
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(CHANNEL, ANOMALY_CHANNEL)
    started = last_beat = time.monotonic()
    try:
        yield "retry: 3000\n\n"
        yield sse_format("ready", {"camera_ids": sorted(camera_ids) if camera_ids else "all"})
        while True:
            message = pubsub.get_message(timeout=1.0)
            now = time.monotonic()
            if message and message.get("type") == "message":
                try:
                    event = json.loads(message["data"])
                except (TypeError, ValueError):
                    continue
                if camera_ids is not None and event.get("camera_id") not in camera_ids:
                    continue
                channel = message.get("channel")
                if channel in (ANOMALY_CHANNEL, ANOMALY_CHANNEL.encode()):
                    yield sse_format("anomaly", event, event_id=f"anomaly-{event['id']}-{event['change']}")
                else:
                    yield sse_format("detection", event, event_id=f"{event['camera_id']}-{event['timestamp']}")
            if now - last_beat >= HEARTBEAT_SECONDS:
                last_beat = now
                yield ": heartbeat\n\n"
            if max_seconds is not None and now - started >= max_seconds:
                return
    finally:
        try:
            pubsub.close()
        except redis.RedisError:
            pass
