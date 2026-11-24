"""Anomaly indications for the operator.

GET  /api/anomalies                    list, newest first (?status ?camera_id ?type ?review)
POST /api/anomalies/<id>/review        operator verdict {"verdict": "true"|"false", "note"}
GET  /api/anomalies/<id>/photo         photo taken when the indication started (JPEG)
GET  /api/anomalies/review-summary     reviewed alerts and precision per camera and type
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, send_file
from flask_jwt_extended import current_user

from ..auth.decorators import roles_required
from ..errors import ApiError, NotFound
from ..models import ROLE_ADMIN, ROLE_OPERATOR
from ..responses import ok
from ..schemas import AnomalyQuery, ReviewIn, ReviewSummaryQuery, parse_body, parse_query
from ..services import anomaly_service, camera_service
from ..services.serializers import anomaly_to_dict

bp = Blueprint("anomalies", __name__, url_prefix="/api/anomalies")


@bp.get("")
@roles_required(ROLE_ADMIN, ROLE_OPERATOR)
def list_anomalies():
    query = parse_query(AnomalyQuery)
    if query.camera_id is not None:
        camera_service.get_camera(query.camera_id)
    rows, total = anomaly_service.list_anomalies(
        status=query.status, camera_id=query.camera_id, type_=query.type,
        page=query.page, per_page=query.per_page, review=query.review,
    )
    return ok([anomaly_to_dict(a, name) for a, name in rows], meta={
        "page": query.page,
        "per_page": query.per_page,
        "total": total,
        "pages": (total + query.per_page - 1) // query.per_page,
        "semantics": "indication",
    })


@bp.post("/<int:anomaly_id>/review")
@roles_required(ROLE_ADMIN, ROLE_OPERATOR)
def review(anomaly_id: int):
    body = parse_body(ReviewIn)
    return ok(anomaly_service.review(anomaly_id, body.verdict, body.note, current_user.username))


@bp.get("/<int:anomaly_id>/photo")
@roles_required(ROLE_ADMIN, ROLE_OPERATOR)
def photo(anomaly_id: int):
    path = anomaly_service.photo_path(anomaly_id)
    if path is None or not path.is_file():
        raise NotFound("Foto anomali tidak tersedia.")
    return send_file(path.resolve(), mimetype="image/jpeg", max_age=3600)


@bp.get("/review-summary")
@roles_required(ROLE_ADMIN, ROLE_OPERATOR)
def review_summary():
    query = parse_query(ReviewSummaryQuery)
    tz = ZoneInfo(current_app.config["REPORT_TIMEZONE"])
    today = datetime.now(tz).date()
    end_day = query.to or today
    start_day = query.from_ or (end_day - timedelta(days=29))
    if start_day > end_day or (end_day - start_day).days > 366:
        raise ApiError("Rentang tanggal tidak valid (maksimal 366 hari).", status=422, code="validation_error")
    start = datetime.combine(start_day, time.min, tz)
    end = datetime.combine(end_day + timedelta(days=1), time.min, tz)
    return ok(anomaly_service.review_summary(start, end), meta={
        "from": start_day.isoformat(), "to": end_day.isoformat(), "timezone": str(tz),
        "precision": "correct / reviewed",
    })
