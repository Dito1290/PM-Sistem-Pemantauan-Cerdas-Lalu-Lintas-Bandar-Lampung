"""Detection storage (FT-04) and history API (UC-03)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from citysight.extensions import db
from citysight.models import Detection
from citysight.pipeline.detector import VehicleCounts
from citysight.services.detection_service import save_detection

T0 = datetime(2026, 10, 22, 2, 0, tzinfo=timezone.utc)  # 09:00 WIB


def test_save_detection_stores_counts_and_total(app, make_camera):
    camera_id = make_camera()
    with app.app_context():
        det = save_detection(camera_id, T0, VehicleCounts(car=3, motorcycle=7, bus=1, truck=2))
        assert det.total_vehicle == 13
        assert det.timestamp == T0
        assert db.session.scalar(select(func.count()).select_from(Detection)) == 1


def test_save_detection_is_idempotent_per_frame(app, make_camera):
    camera_id = make_camera()
    with app.app_context():
        assert save_detection(camera_id, T0, VehicleCounts(car=1)) is not None
        assert save_detection(camera_id, T0, VehicleCounts(car=1)) is None  # retried task
        assert db.session.scalar(select(func.count()).select_from(Detection)) == 1


def test_db_rejects_negative_or_inconsistent_counts(app, make_camera):
    camera_id = make_camera()
    with app.app_context():
        db.session.add(Detection(camera_id=camera_id, timestamp=T0, car_count=-1, total_vehicle=-1))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        db.session.add(Detection(camera_id=camera_id, timestamp=T0, car_count=2, total_vehicle=5))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_db_rejects_unknown_camera(app):
    with app.app_context():
        with pytest.raises(IntegrityError):
            save_detection(4242, T0, VehicleCounts(car=1))
        db.session.rollback()


def _seed(app, camera_id, n, start=T0, step=timedelta(seconds=1)):
    with app.app_context():
        for i in range(n):
            save_detection(camera_id, start + i * step, VehicleCounts(car=i, motorcycle=1))


def test_history_pagination_and_order(app, client, operator_headers, make_camera):
    camera_id = make_camera()
    _seed(app, camera_id, 25)
    url = f"/api/cameras/{camera_id}/detections?from=2026-10-22T02:00:00Z&to=2026-10-22T03:00:00Z"
    res = client.get(url + "&per_page=10&page=2", headers=operator_headers)
    assert res.status_code == 200
    body = res.get_json()
    assert body["meta"] == {**body["meta"], "page": 2, "per_page": 10, "total": 25, "pages": 3,
                            "count_semantics": "per_frame"}
    assert [d["car_count"] for d in body["data"]] == list(range(14, 4, -1))  # newest first
    asc = client.get(url + "&order=asc&per_page=3", headers=operator_headers).get_json()["data"]
    assert [d["car_count"] for d in asc] == [0, 1, 2]
    assert set(asc[0]) == {"id", "camera_id", "timestamp", "car_count", "motorcycle_count",
                           "bus_count", "truck_count", "total_vehicle"}
    assert asc[0]["timestamp"] == "2026-10-22T02:00:00Z"


def test_history_time_filter_with_offset(app, client, operator_headers, make_camera):
    camera_id = make_camera()
    _seed(app, camera_id, 10, step=timedelta(minutes=10))  # 02:00..03:30 UTC
    # 09:30-10:00 WIB == 02:30-03:00 UTC -> rows at 02:30, 02:40, 02:50
    res = client.get(
        f"/api/cameras/{camera_id}/detections?from=2026-10-22T09:30:00%2B07:00&to=2026-10-22T10:00:00%2B07:00",
        headers=operator_headers)
    assert res.get_json()["meta"]["total"] == 3
    # An unencoded "+" (decoded as space) is tolerated too.
    res = client.get(
        f"/api/cameras/{camera_id}/detections?from=2026-10-22T09:30:00+07:00&to=2026-10-22T10:00:00+07:00",
        headers=operator_headers)
    assert res.get_json()["meta"]["total"] == 3


@pytest.mark.parametrize("query", [
    "from=2026-10-22T10:00:00Z&to=2026-10-22T09:00:00Z",   # reversed
    "from=2026-10-22T10:00:00",                            # naive timestamp
    "from=yesterday",
    "from=2026-01-01T00:00:00Z&to=2026-03-01T00:00:00Z",   # > 31 days
    "per_page=501",
    "page=0",
    "order=sideways",
    "page=1&page=2",
    "unknown=1",
])
def test_history_query_validation(client, operator_headers, make_camera, query):
    camera_id = make_camera()
    res = client.get(f"/api/cameras/{camera_id}/detections?{query}", headers=operator_headers)
    assert res.status_code == 422, res.get_json()
    assert res.get_json()["error"]["code"] in {"validation_error", "duplicate_query_param"}


def test_history_unknown_camera(client, operator_headers):
    res = client.get("/api/cameras/77/detections", headers=operator_headers)
    assert res.status_code == 404


def test_history_default_window_is_last_hour(app, client, operator_headers, make_camera):
    camera_id = make_camera()
    now = datetime.now(timezone.utc)
    with app.app_context():
        save_detection(camera_id, now - timedelta(minutes=5), VehicleCounts(car=1))
        save_detection(camera_id, now - timedelta(hours=2), VehicleCounts(car=1))
    body = client.get(f"/api/cameras/{camera_id}/detections", headers=operator_headers).get_json()
    assert body["meta"]["total"] == 1
