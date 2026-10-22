from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db


class HourlyStat(db.Model):
    """Per-camera, per-hour aggregate of ``detections``.

    avg_vehicle      = AVG(total_vehicle) over the detection rows in the hour
    max_vehicle      = MAX(total_vehicle) (most vehicles seen in one frame)
    total_detections = number of detection rows (processed frames) in the hour
    """

    __tablename__ = "hourly_stats"
    __table_args__ = (
        UniqueConstraint("camera_id", "hour_bucket", name="uq_hourly_stats_camera_hour"),
        CheckConstraint("avg_vehicle >= 0", name="avg_nonneg"),
        CheckConstraint("max_vehicle >= 0", name="max_nonneg"),
        CheckConstraint("total_detections > 0", name="detections_positive"),
        CheckConstraint("avg_vehicle <= max_vehicle", name="avg_le_max"),
        CheckConstraint(
            "date_trunc('hour', hour_bucket AT TIME ZONE 'UTC') = hour_bucket AT TIME ZONE 'UTC'",
            name="hour_aligned",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[int] = mapped_column(
        ForeignKey("cameras.id", ondelete="RESTRICT"), nullable=False
    )
    hour_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    avg_vehicle: Mapped[float] = mapped_column(Float, nullable=False)
    max_vehicle: Mapped[int] = mapped_column(Integer, nullable=False)
    total_detections: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
