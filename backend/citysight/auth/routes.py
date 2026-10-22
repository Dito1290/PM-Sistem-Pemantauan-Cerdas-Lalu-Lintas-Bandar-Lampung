"""POST /api/auth/login, POST /api/auth/logout, GET /api/auth/me."""
from __future__ import annotations

import logging

from flask import Blueprint, current_app, request
from flask_jwt_extended import create_access_token, current_user, get_jwt
from sqlalchemy import func, or_, select

from ..extensions import db
from ..models import User
from ..responses import fail, ok
from ..schemas import LoginIn, parse_body
from . import login_limiter
from .decorators import roles_required
from .passwords import verify_password
from .tokens import revoke_token

log = logging.getLogger(__name__)
bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/login")
def login():
    payload = parse_body(LoginIn)
    ip = request.remote_addr or "unknown"

    wait = login_limiter.retry_after(ip, payload.username)
    if wait:
        response, status = fail(429, "too_many_attempts", "Terlalu banyak percobaan masuk. Coba lagi nanti.")
        response.headers["Retry-After"] = str(wait)
        return response, status

    identifier = payload.username.lower()
    user = db.session.scalar(
        select(User).where(or_(func.lower(User.username) == identifier, func.lower(User.email) == identifier))
    )
    if not verify_password(payload.password, user.password_hash if user else None):
        login_limiter.register_failure(ip, payload.username)
        log.info("Failed login for '%s' from %s", payload.username, ip)
        return fail(401, "invalid_credentials", "Nama pengguna atau kata sandi salah.")

    login_limiter.reset(ip, payload.username)
    token = create_access_token(identity=user)
    expires = current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]
    log.info("User %s (%s) logged in", user.username, user.role)
    return ok({
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": int(expires.total_seconds()),
        "user": user.to_dict(),
    })


@bp.post("/logout")
@roles_required()
def logout():
    revoke_token(get_jwt())
    return ok({"message": "Berhasil keluar."})


@bp.get("/me")
@roles_required()
def me():
    return ok(current_user.to_dict())
