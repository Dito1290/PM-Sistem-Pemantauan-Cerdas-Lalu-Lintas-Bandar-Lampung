"""Per-camera frame buffer in Redis.

Layout: Redis list ``frames:{camera_id}``; newest frame at the head (LPUSH).
The list is trimmed to FRAME_QUEUE_MAX after every push, so at most 10 frames
(proposal Bab 5.2.1 c) are ever buffered and old frames cannot pile up.

The consumer takes the newest frame and discards the older ones in a single
MULTI/EXEC transaction. Every frame is therefore processed at most once
(no double counting) and a lagging worker always jumps to the latest frame.
"""
from __future__ import annotations

import struct
import time
from dataclasses import dataclass

import redis

_HEADER = struct.Struct(">d")  # capture time, unix seconds (UTC)


def frames_key(camera_id: int) -> str:
    return f"frames:{camera_id}"


def pending_key(camera_id: int) -> str:
    return f"detect:pending:{camera_id}"


@dataclass(frozen=True)
class QueuedFrame:
    camera_id: int
    captured_at: float
    jpeg: bytes
    discarded: int  # older frames dropped in favour of this one

    @property
    def age(self) -> float:
        return time.time() - self.captured_at


def encode(captured_at: float, jpeg: bytes) -> bytes:
    return _HEADER.pack(captured_at) + jpeg


def decode(payload: bytes) -> tuple[float, bytes]:
    if len(payload) <= _HEADER.size:
        raise ValueError("Frame payload is truncated")
    (captured_at,) = _HEADER.unpack_from(payload)
    return captured_at, payload[_HEADER.size:]


def push_frame(client: redis.Redis, camera_id: int, captured_at: float, jpeg: bytes, max_len: int) -> int:
    """Push a frame and trim the buffer. Returns how many old frames were evicted."""
    key = frames_key(camera_id)
    pipe = client.pipeline(transaction=True)
    pipe.lpush(key, encode(captured_at, jpeg))
    pipe.ltrim(key, 0, max_len - 1)
    pipe.expire(key, 60)  # buffer disappears if the ingest service stops
    length_after_push = pipe.execute()[0]
    return max(0, length_after_push - max_len)


def take_latest(client: redis.Redis, camera_id: int) -> QueuedFrame | None:
    key = frames_key(camera_id)
    pipe = client.pipeline(transaction=True)
    pipe.llen(key)
    pipe.lindex(key, 0)
    pipe.delete(key)
    length, newest, _ = pipe.execute()
    if not newest:
        return None
    captured_at, jpeg = decode(newest)
    return QueuedFrame(camera_id, captured_at, jpeg, discarded=max(0, int(length) - 1))


def queue_length(client: redis.Redis, camera_id: int) -> int:
    return int(client.llen(frames_key(camera_id)))


def claim_detection_slot(client: redis.Redis, camera_id: int, ttl_seconds: int = 15) -> bool:
    """At most one detection task per camera is queued or running at a time."""
    return bool(client.set(pending_key(camera_id), "1", nx=True, ex=ttl_seconds))


def release_detection_slot(client: redis.Redis, camera_id: int) -> None:
    client.delete(pending_key(camera_id))
