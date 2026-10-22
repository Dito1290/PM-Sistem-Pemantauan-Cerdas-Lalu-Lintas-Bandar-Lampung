"""Hourly aggregation (FT-05), idempotency, daily recap and summary."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from citysight.extensions import db
from citysight.models import HourlyStat
from citysight.pipeline.detector import VehicleCounts
from citysight.services import stats_service
from citysight.services.detection_service import save_detection

H = datetime(2026, 10, 22, 2, 0, tzinfo=timezone.utc)


def _add(app, camera_id, at, total):
    with app.app_context():
        save_detection(camera_id, at, VehicleCounts(car=total))


def _rows(app):
    with app.app_context():
        return [(r.camera_id, r.hour_bucket, r.avg_vehicle, r.max_vehicle, r.total_detections)
                for r in db.session.scalars(select(HourlyStat).order_by(HourlyStat.camera_id, HourlyStat.hour_bucket))]


def test_aggregate_hour_values(app, make_camera):
    a, b = make_camera(name="A"), make_camera(name="B")
    for i, total in enumerate([2, 4, 9]):
        _add(app, a, H + timedelta(minutes=i * 10), total)
    _add(app, b, H + timedelta(minutes=59, seconds=59), 5)
    _add(app, a, H + timedelta(hours=1), 100)       # next hour, excluded
    _add(app, a, H - timedelta(microseconds=1), 100)  # previous hour, excluded
    with app.app_context():
        assert stats_service.aggregate_hour(H) == 2
    assert _rows(app) == [(a, H, pytest.approx(5.0), 9, 3), (b, H, 5.0, 5, 1)]


def test_aggregation_is_idempotent(app, make_camera):
    a = make_camera()
    for total in (1, 3):
        _add(app, a, H + timedelta(minutes=total), total)
    with app.app_context():
        stats_service.aggregate_hour(H)
        first = _rows(app)
        stats_service.aggregate_hour(H)
        stats_service.aggregate_hour(H + timedelta(minutes=30))  # same bucket, unaligned input
    assert _rows(app) == first
    assert len(first) == 1 and first[0][4] == 2


def test_rerun_picks_up_late_detections(app, make_camera):
    a = make_camera()
    _add(app, a, H + timedelta(minutes=1), 2)
    with app.app_context():
        stats_service.aggregate_hour(H)
    _add(app, a, H + timedelta(minutes=2), 6)  # arrives late
    with app.app_context():
        stats_service.aggregate_hour(H)
    assert _rows(app) == [(a, H, 4.0, 6, 2)]


def test_aggregate_recent_covers_lookback_without_duplicates(app, make_camera):
    a = make_camera()
    _add(app, a, H + timedelta(minutes=5), 3)
    _add(app, a, H + timedelta(hours=1, minutes=5), 7)
    now = H + timedelta(hours=2, minutes=5)  # beat runs at hh:05
    with app.app_context():
        hours = stats_service.aggregate_recent(now=now, lookback_hours=2)
        stats_service.aggregate_recent(now=now, lookback_hours=2)
    assert hours == [H.isoformat(), (H + timedelta(hours=1)).isoformat()]
    assert [(r[1], r[4]) for r in _rows(app)] == [(H, 1), (H + timedelta(hours=1), 1)]


def test_aggregate_requires_aware_datetime(app):
    with app.app_context(), pytest.raises(ValueError):
        stats_service.aggregate_hour(datetime(2026, 10, 22, 2))


def test_celery_task_runs_aggregation(app, make_camera):
    from citysight.tasks.stats import aggregate_hourly_stats

    a = make_camera()
    _add(app, a, H + timedelta(minutes=5), 3)
    result = aggregate_hourly_stats.apply(kwargs={"now_iso": (H + timedelta(hours=1, minutes=5)).isoformat(),
                                                  "lookback_hours": 1})
    assert result.successful()
    assert _rows(app) == [(a, H, 3.0, 3, 1)]


def test_beat_schedule_configured(app):
    celery = app.extensions["celery"]
    entry = celery.conf.beat_schedule["aggregate-hourly-stats"]
    assert entry["task"] == "citysight.aggregate_hourly_stats"
    assert entry["schedule"].minute == {5}


def test_hourly_endpoint(app, client, operator_headers, make_camera):
    a = make_camera()
    _add(app, a, H + timedelta(minutes=1), 4)
    _add(app, a, H + timedelta(hours=1, minutes=1), 8)
    with app.app_context():
        stats_service.aggregate_range(H, H + timedelta(hours=2))
    res = client.get(f"/api/cameras/{a}/stats/hourly?from=2026-10-22T02:00:00Z&to=2026-10-22T04:00:00Z",
                     headers=operator_headers)
    assert res.status_code == 200
    body = res.get_json()
    assert body["data"] == [
        {"camera_id": a, "hour_bucket": "2026-10-22T02:00:00Z", "avg_vehicle": 4.0, "max_vehicle": 4,
         "total_detections": 1},
        {"camera_id": a, "hour_bucket": "2026-10-22T03:00:00Z", "avg_vehicle": 8.0, "max_vehicle": 8,
         "total_detections": 1},
    ]
    empty = client.get(f"/api/cameras/{a}/stats/hourly?from=2026-01-01T00:00:00Z&to=2026-01-02T00:00:00Z",
                       headers=operator_headers).get_json()
    assert empty["data"] == [] and empty["meta"]["count"] == 0
    assert client.get("/api/cameras/999/stats/hourly", headers=operator_headers).status_code == 404


def test_daily_endpoint_weighted_average_in_wib(app, client, operator_headers, make_camera):
    a = make_camera()
    # 2026-10-22 16:30 UTC == 23:30 WIB (day 22); 17:30 UTC == 00:30 WIB (day 23)
    for minute, total in [(0, 2), (1, 2), (2, 2)]:
        _add(app, a, datetime(2026, 10, 22, 16, minute, tzinfo=timezone.utc), total)
    _add(app, a, datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc), 10)
    _add(app, a, datetime(2026, 10, 22, 17, 30, tzinfo=timezone.utc), 7)
    with app.app_context():
        stats_service.aggregate_range(datetime(2026, 10, 22, 14, tzinfo=timezone.utc),
                                      datetime(2026, 10, 22, 18, tzinfo=timezone.utc))
    res = client.get(f"/api/cameras/{a}/stats/daily?from=2026-10-22&to=2026-10-23", headers=operator_headers)
    assert res.status_code == 200
    data = res.get_json()["data"]
    # Day 22 WIB: frames 2,2,2,10 -> avg 4.0 (weighted), not mean of hourly avgs (6.0)
    assert data == [
        {"date": "2026-10-22", "avg_vehicle": 4.0, "max_vehicle": 10, "total_detections": 4, "hours_with_data": 2},
        {"date": "2026-10-23", "avg_vehicle": 7.0, "max_vehicle": 7, "total_detections": 1, "hours_with_data": 1},
    ]
    assert client.get(f"/api/cameras/{a}/stats/daily?from=2026-10-23&to=2026-10-01",
                      headers=operator_headers).status_code == 422
    assert client.get(f"/api/cameras/{a}/stats/daily?from=2026-10-23T00:00:00Z",
                      headers=operator_headers).status_code == 422


def test_summary(app, client, operator_headers, make_camera):
    a = make_camera(name="A", latitude=-5.4, longitude=105.26)
    b = make_camera(name="B", status="inactive")
    now = datetime.now(timezone.utc)
    with app.app_context():
        save_detection(a, now - timedelta(minutes=2), VehicleCounts(car=1, motorcycle=2))
        save_detection(a, now - timedelta(minutes=1), VehicleCounts(car=2, motorcycle=3, bus=1, truck=1))
    res = client.get("/api/stats/summary", headers=operator_headers)
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["cameras"] == {"total": 2, "active": 1, "inactive": 1, "online": 0, "max_active": 3}
    assert data["current_vehicles"] == {"car_count": 2, "motorcycle_count": 3, "bus_count": 1,
                                        "truck_count": 1, "total_vehicle": 7}
    cam_a = next(c for c in data["per_camera"] if c["id"] == a)
    assert cam_a["latest_detection"]["total_vehicle"] == 7
    assert cam_a["last_hour"] == {"avg_vehicle": 5.0, "max_vehicle": 7, "total_detections": 2}
    assert cam_a["latitude"] == pytest.approx(-5.4)
    cam_b = next(c for c in data["per_camera"] if c["id"] == b)
    assert cam_b["latest_detection"] is None and cam_b["stream_state"] == "offline"


def test_summary_with_no_cameras(client, operator_headers):
    data = client.get("/api/stats/summary", headers=operator_headers).get_json()["data"]
    assert data["cameras"]["total"] == 0 and data["per_camera"] == []
