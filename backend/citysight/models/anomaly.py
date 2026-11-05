from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db

ANOMALY_HIGH_DENSITY = "high_density"
ANOMALY_CAMERA_OFFLINE = "camera_offline"
ANOMALY_TYPES = (ANOMALY_HIGH_DENSITY, ANOMALY_CAMERA_OFFLINE)


class Anomaly(db.Model):
    """An indication for the operator, not a confirmed incident.

    high_density   - the vehicles per frame stayed far above what this camera
                     usually shows (possible jam, accident, event, road closure)
    camera_offline - no frame of this active camera was processed for a while

    ``ended_at IS NULL`` means still active. The partial unique index allows
    at most one active anomaly per camera and type.
    """

    __tablename__ = "anomalies"
    __table_args__ = (
        CheckConstraint("type IN ('high_density', 'camera_offline')", name="type_valid"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ended_after_start"),
        Index("uq_anomalies_active", "camera_id", "type", unique=True,
              postgresql_where=text("ended_at IS NULL")),
        Index("ix_anomalies_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[int] = mapped_column(
        ForeignKey("cameras.id", ondelete="RESTRICT"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    @property
    def is_active(self) -> bool:
        return self.ended_at is None
