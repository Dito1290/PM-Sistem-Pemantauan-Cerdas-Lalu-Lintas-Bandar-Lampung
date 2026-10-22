"""Camera CRUD rules.

* Only non-deleted cameras are visible.
* At most MAX_ACTIVE_CAMERAS (3) can be ``active`` at once (proposal Tabel 2).
* DELETE is a soft delete: status -> inactive, deleted_at set. Detections and
  hourly stats keep their foreign key, so research data is not lost, and the
  name becomes reusable.
"""
from __future__ import annotations

from flask import current_app
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from ..errors import ApiError, Conflict, NotFound
from ..extensions import db
from ..models import Camera
from ..pipeline.sources import InvalidStreamUrl, validate_stream_url
from ..schemas import CameraCreateIn, CameraUpdateIn
from ..timeutil import utcnow

_ACTIVE_LOCK_ID = 7_424_201  # pg advisory lock serialising activation checks


def list_cameras(status: str | None = None) -> list[Camera]:
    query = select(Camera).where(Camera.deleted_at.is_(None)).order_by(Camera.id)
    if status:
        query = query.where(Camera.status == status)
    return list(db.session.scalars(query))


def get_camera(camera_id: int) -> Camera:
    camera = db.session.get(Camera, camera_id)
    if camera is None or camera.is_deleted:
        raise NotFound(f"Kamera dengan id {camera_id} tidak ditemukan.")
    return camera


def _check_url(url: str) -> str:
    cfg = current_app.config
    try:
        return validate_stream_url(
            url,
            schemes=cfg["STREAM_ALLOWED_SCHEMES"],
            hosts=cfg["STREAM_ALLOWED_HOSTS"],
            allow_files=cfg["ALLOW_FILE_SOURCES"],
        )
    except InvalidStreamUrl as exc:
        raise ApiError(str(exc), status=422, code="validation_error",
                       details=[{"field": "stream_url", "message": str(exc)}]) from exc


def _ensure_activation_allowed(exclude_id: int | None = None) -> None:
    db.session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _ACTIVE_LOCK_ID})
    query = select(func.count()).select_from(Camera).where(
        Camera.deleted_at.is_(None), Camera.status == "active"
    )
    if exclude_id is not None:
        query = query.where(Camera.id != exclude_id)
    limit = current_app.config["MAX_ACTIVE_CAMERAS"]
    if db.session.scalar(query) >= limit:
        raise Conflict(
            f"Maksimal {limit} kamera aktif. Nonaktifkan kamera lain terlebih dahulu.",
            code="active_camera_limit",
        )


def _commit_or_conflict() -> None:
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        if "uq_cameras_name_live" in str(exc.orig):
            raise Conflict("Nama kamera sudah digunakan.", code="duplicate_name") from exc
        raise


def create_camera(data: CameraCreateIn) -> Camera:
    stream_url = _check_url(data.stream_url)
    if data.status == "active":
        _ensure_activation_allowed()
    camera = Camera(
        name=data.name,
        location=data.location,
        latitude=data.latitude,
        longitude=data.longitude,
        stream_url=stream_url,
        status=data.status,
    )
    db.session.add(camera)
    _commit_or_conflict()
    return camera


def update_camera(camera_id: int, data: CameraUpdateIn) -> Camera:
    camera = get_camera(camera_id)
    changes = data.model_dump(include=data.model_fields_set)
    if "stream_url" in changes:
        changes["stream_url"] = _check_url(changes["stream_url"])
    if changes.get("status") == "active" and camera.status != "active":
        _ensure_activation_allowed(exclude_id=camera.id)
    for field, value in changes.items():
        setattr(camera, field, value)
    _commit_or_conflict()
    return camera


def delete_camera(camera_id: int) -> None:
    camera = get_camera(camera_id)
    camera.status = "inactive"
    camera.deleted_at = utcnow()
    db.session.commit()
