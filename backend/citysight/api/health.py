"""GET /api/health - unauthenticated liveness/readiness check (no internals)."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from ..extensions import db
from ..redis_client import get_redis

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    checks = {}
    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001
        db.session.rollback()
        checks["database"] = "error"
    try:
        get_redis(current_app.config["REDIS_URL"]).ping()
        checks["redis"] = "ok"
    except Exception:  # noqa: BLE001
        checks["redis"] = "error"
    healthy = all(v == "ok" for v in checks.values())
    return jsonify({"status": "ok" if healthy else "degraded", "checks": checks}), 200 if healthy else 503
