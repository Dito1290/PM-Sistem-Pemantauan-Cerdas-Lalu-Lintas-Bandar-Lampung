"""Hourly aggregation and statistics queries.

Definitions (documented in docs/DATABASE_DESIGN.md):
* avg_vehicle      - mean of detections.total_vehicle for the camera/hour
                     (average number of vehicles visible per processed frame)
* max_vehicle      - highest total_vehicle seen in a single frame that hour
* total_detections - number of detection rows (processed frames) that hour

These are per-frame visibility statistics, not counts of unique vehicles.

Aggregation is idempotent: each run recomputes the hour from ``detections``
and upserts on (camera_id, hour_bucket), so re-running never duplicates or
double-adds. Rows for cameras that no longer have detections in that hour
are removed so the table always mirrors the source data.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import text

from ..extensions import db
from ..timeutil import floor_hour, previous_full_hour, utcnow

log = logging.getLogger(__name__)

_UPSERT = text("""
    INSERT INTO hourly_stats (camera_id, hour_bucket, avg_vehicle, max_vehicle, total_detections, computed_at)
    SELECT d.camera_id, :hour, AVG(d.total_vehicle)::double precision, MAX(d.total_vehicle), COUNT(*), now()
    FROM detections d
    WHERE d.timestamp >= :hour AND d.timestamp < :hour_end
      AND (CAST(:camera_id AS integer) IS NULL OR d.camera_id = :camera_id)
    GROUP BY d.camera_id
    ON CONFLICT (camera_id, hour_bucket) DO UPDATE SET
        avg_vehicle = EXCLUDED.avg_vehicle,
        max_vehicle = EXCLUDED.max_vehicle,
        total_detections = EXCLUDED.total_detections,
        computed_at = now()
""")

_PRUNE = text("""
    DELETE FROM hourly_stats h
    WHERE h.hour_bucket = :hour
      AND (CAST(:camera_id AS integer) IS NULL OR h.camera_id = :camera_id)
      AND NOT EXISTS (
          SELECT 1 FROM detections d
          WHERE d.camera_id = h.camera_id AND d.timestamp >= :hour AND d.timestamp < :hour_end
      )
""")


def aggregate_hour(hour: datetime, camera_id: int | None = None) -> int:
    """Recompute one hour bucket. Returns the number of camera rows written."""
    if hour.tzinfo is None:
        raise ValueError("hour must be timezone-aware")
    hour = floor_hour(hour)
    params = {"hour": hour, "hour_end": hour + timedelta(hours=1), "camera_id": camera_id}
    try:
        written = db.session.execute(_UPSERT, params).rowcount
        db.session.execute(_PRUNE, params)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    log.info("Aggregated hour %s (camera=%s): %s row(s)", hour.isoformat(), camera_id or "all", written)
    return written


def aggregate_recent(now: datetime | None = None, lookback_hours: int | None = None) -> list[str]:
    """Aggregate the last N completed hours (covers late rows and missed runs)."""
    lookback = lookback_hours or current_app.config["HOURLY_AGGREGATION_LOOKBACK_HOURS"]
    last = previous_full_hour(now)
    hours = [last - timedelta(hours=i) for i in range(lookback)][::-1]
    for hour in hours:
        aggregate_hour(hour)
    return [h.isoformat() for h in hours]


def aggregate_range(start: datetime, end: datetime) -> int:
    """Backfill every hour in [start, end). Returns hours processed."""
    hour = floor_hour(start)
    count = 0
    while hour < end:
        aggregate_hour(hour)
        hour += timedelta(hours=1)
        count += 1
    return count


def hourly_stats(camera_id: int, start: datetime, end: datetime):
    from sqlalchemy import select

    from ..models import HourlyStat

    return list(db.session.scalars(
        select(HourlyStat)
        .where(HourlyStat.camera_id == camera_id, HourlyStat.hour_bucket >= floor_hour(start),
               HourlyStat.hour_bucket < end)
        .order_by(HourlyStat.hour_bucket)
    ))


def daily_stats(camera_id: int, start: date, end: date) -> list[dict]:
    """Daily recap (FR-05) derived exactly from hourly_stats.

    Days follow REPORT_TIMEZONE (WIB). avg_vehicle is weighted by
    total_detections so it equals the mean over all frames of that day.
    """
    tz = current_app.config["REPORT_TIMEZONE"]
    rows = db.session.execute(text("""
        SELECT (h.hour_bucket AT TIME ZONE :tz)::date AS day,
               SUM(h.avg_vehicle * h.total_detections) / SUM(h.total_detections) AS avg_vehicle,
               MAX(h.max_vehicle) AS max_vehicle,
               SUM(h.total_detections) AS total_detections,
               COUNT(*) AS hours_with_data
        FROM hourly_stats h
        WHERE h.camera_id = :camera_id
          AND (h.hour_bucket AT TIME ZONE :tz)::date BETWEEN :start AND :end
        GROUP BY day ORDER BY day
    """), {"tz": tz, "camera_id": camera_id, "start": start, "end": end}).mappings()
    return [
        {
            "date": row["day"].isoformat(),
            "avg_vehicle": round(float(row["avg_vehicle"]), 2),
            "max_vehicle": int(row["max_vehicle"]),
            "total_detections": int(row["total_detections"]),
            "hours_with_data": int(row["hours_with_data"]),
        }
        for row in rows
    ]


def summary(camera_ids: list[int]) -> dict:
    """System-wide overview for the dashboard."""
    if not camera_ids:
        return {"latest": {}, "last_hour": {}, "last_24h": {}}
    now = utcnow()
    latest = db.session.execute(text("""
        SELECT c.id AS camera_id, d.timestamp, d.car_count, d.motorcycle_count, d.bus_count,
               d.truck_count, d.total_vehicle
        FROM unnest(CAST(:ids AS integer[])) AS c(id)
        CROSS JOIN LATERAL (
            SELECT * FROM detections d WHERE d.camera_id = c.id ORDER BY d.timestamp DESC LIMIT 1
        ) d
    """), {"ids": camera_ids}).mappings()
    last_hour = db.session.execute(text("""
        SELECT camera_id, AVG(total_vehicle)::double precision AS avg_vehicle,
               MAX(total_vehicle) AS max_vehicle, COUNT(*) AS total_detections
        FROM detections
        WHERE camera_id = ANY(CAST(:ids AS integer[])) AND timestamp >= :since
        GROUP BY camera_id
    """), {"ids": camera_ids, "since": now - timedelta(hours=1)}).mappings()
    last_day = db.session.execute(text("""
        SELECT camera_id,
               SUM(avg_vehicle * total_detections) / SUM(total_detections) AS avg_vehicle,
               MAX(max_vehicle) AS max_vehicle, SUM(total_detections) AS total_detections
        FROM hourly_stats
        WHERE camera_id = ANY(CAST(:ids AS integer[])) AND hour_bucket >= :since
        GROUP BY camera_id
    """), {"ids": camera_ids, "since": floor_hour(now) - timedelta(hours=24)}).mappings()

    def _agg(row):
        return {
            "avg_vehicle": round(float(row["avg_vehicle"]), 2),
            "max_vehicle": int(row["max_vehicle"]),
            "total_detections": int(row["total_detections"]),
        }

    from ..timeutil import isoformat

    return {
        "latest": {
            row["camera_id"]: {
                "timestamp": isoformat(row["timestamp"]),
                "car_count": row["car_count"],
                "motorcycle_count": row["motorcycle_count"],
                "bus_count": row["bus_count"],
                "truck_count": row["truck_count"],
                "total_vehicle": row["total_vehicle"],
            }
            for row in latest
        },
        "last_hour": {row["camera_id"]: _agg(row) for row in last_hour},
        "last_24h": {row["camera_id"]: _agg(row) for row in last_day},
    }


def local_today() -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(timezone.utc).astimezone(ZoneInfo(current_app.config["REPORT_TIMEZONE"])).date()
