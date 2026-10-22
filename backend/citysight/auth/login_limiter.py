"""Redis-backed brute-force protection for POST /api/auth/login."""
from __future__ import annotations

import hashlib

from flask import current_app

from ..redis_client import get_redis


def _key(ip: str, username: str) -> str:
    digest = hashlib.sha256(f"{ip}|{username.lower()}".encode()).hexdigest()[:32]
    return f"login:fail:{digest}"


def retry_after(ip: str, username: str) -> int:
    """Seconds until another attempt is allowed, or 0 if not locked."""
    client = get_redis(current_app.config["REDIS_URL"])
    key = _key(ip, username)
    attempts = int(client.get(key) or 0)
    if attempts >= current_app.config["LOGIN_MAX_ATTEMPTS"]:
        return max(1, int(client.ttl(key)))
    return 0


def register_failure(ip: str, username: str) -> None:
    client = get_redis(current_app.config["REDIS_URL"])
    key = _key(ip, username)
    pipe = client.pipeline()
    pipe.incr(key)
    pipe.expire(key, current_app.config["LOGIN_LOCKOUT_SECONDS"])
    pipe.execute()


def reset(ip: str, username: str) -> None:
    get_redis(current_app.config["REDIS_URL"]).delete(_key(ip, username))
