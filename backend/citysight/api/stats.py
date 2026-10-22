"""GET /api/stats/summary."""
from __future__ import annotations

from flask import Blueprint, current_app

from ..auth.decorators import roles_required
from ..models import ROLE_ADMIN, ROLE_OPERATOR
from ..pipeline import camera_state
from ..redis_client import get_redis
from ..responses import ok
from ..services import camera_service, stats_service
from ..timeutil import isoformat, utcnow

bp = Blueprint("stats", __name__, url_prefix="/api/stats")


@bp.get("/summary")
@roles_required(ROLE_ADMIN, ROLE_OPERATOR)
def summary():
    cameras = camera_service.list_cameras()
    ids = [c.id for c in cameras]
    states = camera_state.read_states(get_redis(current_app.config["REDIS_URL"]), ids)
    agg = stats_service.summary(ids)

    per_camera = []
    for camera in cameras:
        per_camera.append({
            "id": camera.id,
            "name": camera.name,
            "location": camera.location,
            "latitude": float(camera.latitude) if camera.latitude is not None else None,
            "longitude": float(camera.longitude) if camera.longitude is not None else None,
            "status": camera.status,
            "stream_state": states.get(camera.id, {}).get("state", "unknown"),
            "latest_detection": agg["latest"].get(camera.id),
            "last_hour": agg["last_hour"].get(camera.id),
            "last_24h": agg["last_24h"].get(camera.id),
        })

    latest = [c["latest_detection"] for c in per_camera if c["latest_detection"]]
    online = sum(1 for c in per_camera if c["stream_state"] == "online")
    return ok({
        "generated_at": isoformat(utcnow()),
        "cameras": {
            "total": len(cameras),
            "active": sum(1 for c in cameras if c.status == "active"),
            "inactive": sum(1 for c in cameras if c.status == "inactive"),
            "online": online,
            "max_active": current_app.config["MAX_ACTIVE_CAMERAS"],
        },
        "current_vehicles": {
            # Sum of the latest per-frame counts of every camera.
            "car_count": sum(d["car_count"] for d in latest),
            "motorcycle_count": sum(d["motorcycle_count"] for d in latest),
            "bus_count": sum(d["bus_count"] for d in latest),
            "truck_count": sum(d["truck_count"] for d in latest),
            "total_vehicle": sum(d["total_vehicle"] for d in latest),
        },
        "per_camera": per_camera,
        "count_semantics": "per_frame",
    })
