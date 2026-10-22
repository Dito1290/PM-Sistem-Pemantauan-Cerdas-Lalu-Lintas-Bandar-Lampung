"""GET /api/stream/detections - Server-Sent Events for live dashboard tiles.

Browsers' EventSource cannot send headers, so this endpoint (and only this
one) also accepts the JWT as ``?access_token=``. Use HTTPS in deployment.
"""
from __future__ import annotations

from flask import Blueprint, Response, current_app, request, stream_with_context

from ..auth.decorators import roles_required
from ..errors import ApiError
from ..extensions import db
from ..models import ROLE_ADMIN, ROLE_OPERATOR
from ..redis_client import get_redis
from ..services import camera_service
from ..services.realtime import stream_events

bp = Blueprint("stream", __name__, url_prefix="/api/stream")


@bp.get("/detections")
@roles_required(ROLE_ADMIN, ROLE_OPERATOR, locations=["headers", "query_string"])
def detections():
    raw = request.args.get("camera_id")
    camera_ids = None
    if raw:
        try:
            camera_ids = {int(part) for part in raw.split(",") if part.strip()}
        except ValueError as exc:
            raise ApiError("camera_id harus berupa daftar angka dipisah koma.", status=422,
                           code="validation_error") from exc
        for camera_id in camera_ids:
            camera_service.get_camera(camera_id)

    # Release the DB connection now; the stream can stay open for hours.
    db.session.close()
    client = get_redis(current_app.config["REDIS_URL"])
    client.ping()  # fail fast with 503 rather than an empty stream
    max_seconds = current_app.config.get("SSE_MAX_SECONDS")
    response = Response(
        stream_with_context(stream_events(client, camera_ids, max_seconds=max_seconds)),
        mimetype="text/event-stream",
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response
