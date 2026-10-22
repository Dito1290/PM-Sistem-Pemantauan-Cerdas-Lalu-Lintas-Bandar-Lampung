"""Celery tasks for hourly aggregation (scheduled by Celery Beat)."""
from __future__ import annotations

import logging
from datetime import datetime

from celery import shared_task

from ..services import stats_service

log = logging.getLogger(__name__)
AGGREGATE_TASK = "citysight.aggregate_hourly_stats"


@shared_task(name=AGGREGATE_TASK, bind=True, autoretry_for=(Exception,), retry_backoff=60,
             retry_backoff_max=600, max_retries=5, ignore_result=False)
def aggregate_hourly_stats(self, now_iso: str | None = None, lookback_hours: int | None = None) -> list[str]:
    """Recompute the last completed hour(s). Safe to run repeatedly."""
    now = datetime.fromisoformat(now_iso) if now_iso else None
    try:
        return stats_service.aggregate_recent(now=now, lookback_hours=lookback_hours)
    except Exception:
        log.exception("Hourly aggregation failed (attempt %s)", self.request.retries + 1)
        raise
