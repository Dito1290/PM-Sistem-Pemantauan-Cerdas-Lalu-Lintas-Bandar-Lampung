"""JSON shapes shared by the REST API and realtime events."""
from __future__ import annotations

from ..models import Camera, Detection, HourlyStat
from ..timeutil import isoformat


def _num(value):
    return float(value) if value is not None else None


def camera_to_dict(camera: Camera, *, include_stream_url: bool, stream_state: dict | None = None) -> dict:
    data = {
        "id": camera.id,
        "name": camera.name,
        "location": camera.location,
        "latitude": _num(camera.latitude),
        "longitude": _num(camera.longitude),
        "status": camera.status,
        "added_at": isoformat(camera.added_at),
        "updated_at": isoformat(camera.updated_at),
    }
    if include_stream_url:
        # Stream URLs may embed access tokens; only admins receive them.
        data["stream_url"] = camera.stream_url
    if stream_state is not None:
        data["stream"] = stream_state
    return data


def detection_to_dict(det: Detection) -> dict:
    return {
        "id": det.id,
        "camera_id": det.camera_id,
        "timestamp": isoformat(det.timestamp),
        "car_count": det.car_count,
        "motorcycle_count": det.motorcycle_count,
        "bus_count": det.bus_count,
        "truck_count": det.truck_count,
        "total_vehicle": det.total_vehicle,
    }


def hourly_to_dict(stat: HourlyStat) -> dict:
    return {
        "camera_id": stat.camera_id,
        "hour_bucket": isoformat(stat.hour_bucket),
        "avg_vehicle": round(stat.avg_vehicle, 2),
        "max_vehicle": stat.max_vehicle,
        "total_detections": stat.total_detections,
    }
