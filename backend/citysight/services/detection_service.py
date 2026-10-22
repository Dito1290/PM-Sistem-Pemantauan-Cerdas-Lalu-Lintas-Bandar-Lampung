"""Persisting and reading per-frame detection counts."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from ..extensions import db
from ..models import Detection
from ..pipeline.detector import VehicleCounts


def save_detection(camera_id: int, captured_at: datetime, counts: VehicleCounts) -> Detection | None:
    """Insert one row per processed frame.

    ON CONFLICT DO NOTHING on (camera_id, timestamp) makes a retried task for
    the same frame a no-op instead of a duplicate row. Returns None in that case.
    """
    stmt = (
        insert(Detection)
        .values(
            camera_id=camera_id,
            timestamp=captured_at,
            car_count=counts.car,
            motorcycle_count=counts.motorcycle,
            bus_count=counts.bus,
            truck_count=counts.truck,
            total_vehicle=counts.total,
        )
        .on_conflict_do_nothing(constraint="uq_detections_camera_timestamp")
        .returning(Detection.id)
    )
    new_id = db.session.execute(stmt).scalar()
    db.session.commit()
    return db.session.get(Detection, new_id) if new_id is not None else None


def list_detections(camera_id: int, start: datetime, end: datetime, *, page: int, per_page: int,
                    order: str) -> tuple[list[Detection], int]:
    where = (Detection.camera_id == camera_id, Detection.timestamp >= start, Detection.timestamp < end)
    total = db.session.scalar(select(func.count()).select_from(Detection).where(*where))
    ordering = Detection.timestamp.asc() if order == "asc" else Detection.timestamp.desc()
    rows = db.session.scalars(
        select(Detection).where(*where).order_by(ordering).limit(per_page).offset((page - 1) * per_page)
    )
    return list(rows), int(total or 0)
