"""GET /api/anomalies - anomaly indications for the operator (newest first)."""
from __future__ import annotations

from flask import Blueprint

from ..auth.decorators import roles_required
from ..models import ROLE_ADMIN, ROLE_OPERATOR
from ..responses import ok
from ..schemas import AnomalyQuery, parse_query
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
        page=query.page, per_page=query.per_page,
    )
    return ok([anomaly_to_dict(a, name) for a, name in rows], meta={
        "page": query.page,
        "per_page": query.per_page,
        "total": total,
        "pages": (total + query.per_page - 1) // query.per_page,
        "semantics": "indication",
    })
