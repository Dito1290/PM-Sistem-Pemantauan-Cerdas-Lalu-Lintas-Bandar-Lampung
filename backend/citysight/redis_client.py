"""Shared Redis connection.

``REDIS_URL=fakeredis://`` gives an in-process fake, used only by the tests.
"""
from __future__ import annotations

import redis

_clients: dict[str, redis.Redis] = {}


def get_redis(url: str) -> redis.Redis:
    client = _clients.get(url)
    if client is None:
        if url.startswith("fakeredis://"):
            import fakeredis

            client = fakeredis.FakeRedis()
        else:
            client = redis.Redis.from_url(
                url, socket_timeout=5, socket_connect_timeout=5, health_check_interval=30
            )
        _clients[url] = client
    return client


def reset_clients() -> None:
    _clients.clear()
