from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db


class Detection(db.Model):
    """Vehicle counts visible in ONE processed frame (not unique vehicles).

    ``timestamp`` is the frame capture time. The (camera_id, timestamp) unique
    constraint doubles as the history index and makes inserts idempotent if a
    Celery task is retried for the same frame.
    """

    __tablename__ = "detections"
    __table_args__ = (
        UniqueConstraint("camera_id", "timestamp", name="uq_detections_camera_timestamp"),
        CheckConstraint("car_count >= 0", name="car_nonneg"),
        CheckConstraint("motorcycle_count >= 0", name="motorcycle_nonneg"),
        CheckConstraint("bus_count >= 0", name="bus_nonneg"),
        CheckConstraint("truck_count >= 0", name="truck_nonneg"),
        CheckConstraint(
            "total_vehicle = car_count + motorcycle_count + bus_count + truck_count",
            name="total_matches",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    camera_id: Mapped[int] = mapped_column(
        ForeignKey("cameras.id", ondelete="RESTRICT"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    car_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    motorcycle_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bus_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    truck_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_vehicle: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
