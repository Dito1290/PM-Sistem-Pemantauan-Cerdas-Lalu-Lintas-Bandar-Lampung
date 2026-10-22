"""Timezone helpers. All timestamps are stored as timezone-aware UTC."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def floor_hour(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def previous_full_hour(now: datetime | None = None) -> datetime:
    """Start of the last hour that has fully elapsed."""
    return floor_hour(now or utcnow()) - timedelta(hours=1)


def isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
