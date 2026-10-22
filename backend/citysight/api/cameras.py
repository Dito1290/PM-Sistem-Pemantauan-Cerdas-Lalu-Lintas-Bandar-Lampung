"""Camera, detection-history and per-camera statistics endpoints."""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, current_app
from flask_jwt_extended import current_user

from ..auth.decorators import roles_required
from ..errors import ApiError
from ..models import ROLE_ADMIN, ROLE_OPERATOR
from ..pipeline import camera_state
from ..redis_client import get_redis
from ..responses import ok
from ..schemas import (CameraCreateIn, CameraListQuery, CameraUpdateIn, DailyQuery, DetectionQuery,
                       HourlyQuery, parse_body, parse_query)
from ..services import camera_service, detection_service, stats_service
from ..services.serializers import camera_to_dict, detection_to_dict, hourly_to_dict
from ..timeutil import isoformat

bp = Blueprint("cameras", __name__, url_prefix="/api/cameras")
ANY_ROLE = (ROLE_ADMIN, ROLE_OPERATOR)


def _states(ids: list[int]) -> dict[int, dict]:
    return camera_state.read_states(get_redis(current_app.config["REDIS_URL"]), ids)


def _serialize(camera, state=None):
    return camera_to_dict(camera, include_stream_url=current_user.role == ROLE_ADMIN, stream_state=state)


@bp.get("")
@roles_required(*ANY_ROLE)
def list_cameras():
    query = parse_query(CameraListQuery)
    cameras = camera_service.list_cameras(query.status)
    states = _states([c.id for c in cameras])
    return ok([_serialize(c, states.get(c.id)) for c in cameras],
              meta={"count": len(cameras), "max_active": current_app.config["MAX_ACTIVE_CAMERAS"]})


@bp.post("")
@roles_required(ROLE_ADMIN)
def create_camera():
    camera = camera_service.create_camera(parse_body(CameraCreateIn))
    return ok(_serialize(camera), status=201)


@bp.get("/<int:camera_id>")
@roles_required(*ANY_ROLE)
def get_camera(camera_id: int):
    camera = camera_service.get_camera(camera_id)
    return ok(_serialize(camera, _states([camera.id]).get(camera.id)))


@bp.put("/<int:camera_id>")
@roles_required(ROLE_ADMIN)
def update_camera(camera_id: int):
    camera = camera_service.update_camera(camera_id, parse_body(CameraUpdateIn))
    return ok(_serialize(camera))


@bp.delete("/<int:camera_id>")
@roles_required(ROLE_ADMIN)
def delete_camera(camera_id: int):
    camera_service.delete_camera(camera_id)
    return "", 204


@bp.get("/<int:camera_id>/detections")
@roles_required(*ANY_ROLE)
def list_detections(camera_id: int):
    camera_service.get_camera(camera_id)
    query = parse_query(DetectionQuery)
    rows, total = detection_service.list_detections(
        camera_id, query.from_, query.to, page=query.page, per_page=query.per_page, order=query.order
    )
    return ok([detection_to_dict(r) for r in rows], meta={
        "page": query.page,
        "per_page": query.per_page,
        "total": total,
        "pages": (total + query.per_page - 1) // query.per_page,
        "from": isoformat(query.from_),
        "to": isoformat(query.to),
        "order": query.order,
        "count_semantics": "per_frame",
    })


@bp.get("/<int:camera_id>/stats/hourly")
@roles_required(*ANY_ROLE)
def hourly(camera_id: int):
    camera_service.get_camera(camera_id)
    query = parse_query(HourlyQuery)
    rows = stats_service.hourly_stats(camera_id, query.from_, query.to)
    return ok([hourly_to_dict(r) for r in rows], meta={
        "from": isoformat(query.from_),
        "to": isoformat(query.to),
        "count": len(rows),
        "count_semantics": "per_frame",
    })


@bp.get("/<int:camera_id>/stats/daily")
@roles_required(*ANY_ROLE)
def daily(camera_id: int):
    camera_service.get_camera(camera_id)
    query = parse_query(DailyQuery)
    end = query.to or stats_service.local_today()
    start = query.from_ or (end - timedelta(days=6))
    if (end - start).days > 366 or start > end:
        raise ApiError("Rentang tanggal tidak valid (maksimal 366 hari).", status=422, code="validation_error")
    rows = stats_service.daily_stats(camera_id, start, end)
    return ok(rows, meta={
        "from": start.isoformat(),
        "to": end.isoformat(),
        "timezone": current_app.config["REPORT_TIMEZONE"],
        "count": len(rows),
        "count_semantics": "per_frame",
    })
