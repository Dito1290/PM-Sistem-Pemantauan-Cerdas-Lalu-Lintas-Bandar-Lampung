"""JWT wiring: claims, user loading, revocation (logout) and error responses."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis
from flask import Flask, current_app

from ..errors import ServiceUnavailable
from ..extensions import db, jwt
from ..models import User
from ..redis_client import get_redis
from ..responses import fail

log = logging.getLogger(__name__)
BLOCKLIST_PREFIX = "jwt:blocklist:"


def revoke_token(jwt_payload: dict) -> None:
    """Store the token id in Redis until the token would have expired anyway."""
    expires = datetime.fromtimestamp(jwt_payload["exp"], tz=timezone.utc)
    ttl = max(1, int((expires - datetime.now(timezone.utc)).total_seconds()))
    get_redis(current_app.config["REDIS_URL"]).set(BLOCKLIST_PREFIX + jwt_payload["jti"], "1", ex=ttl)


def init_jwt(app: Flask) -> None:
    @jwt.additional_claims_loader
    def _claims(user: User):
        return {"role": user.role, "username": user.username}

    @jwt.user_identity_loader
    def _identity(user: User):
        return str(user.id)

    @jwt.user_lookup_loader
    def _lookup(_header, payload):
        # Re-read the user so role changes / removed accounts take effect
        # immediately instead of trusting the role baked into the token.
        try:
            return db.session.get(User, int(payload["sub"]))
        except (TypeError, ValueError):
            return None

    @jwt.token_in_blocklist_loader
    def _revoked(_header, payload) -> bool:
        try:
            return bool(get_redis(current_app.config["REDIS_URL"]).exists(BLOCKLIST_PREFIX + payload["jti"]))
        except redis.RedisError as error:
            # Fail closed: without the blocklist we cannot honour logout.
            log.error("Cannot check token blocklist: %s", error)
            raise ServiceUnavailable("Layanan sesi sedang tidak tersedia.") from error

    @jwt.expired_token_loader
    def _expired(_header, _payload):
        return fail(401, "token_expired", "Sesi telah berakhir. Silakan masuk kembali.")

    @jwt.invalid_token_loader
    def _invalid(_reason):
        return fail(401, "invalid_token", "Token tidak valid.")

    @jwt.unauthorized_loader
    def _missing(_reason):
        return fail(401, "missing_token", "Autentikasi diperlukan.")

    @jwt.revoked_token_loader
    def _revoked_response(_header, _payload):
        return fail(401, "token_revoked", "Token sudah tidak berlaku. Silakan masuk kembali.")

    @jwt.user_lookup_error_loader
    def _lookup_error(_header, _payload):
        return fail(401, "invalid_token", "Akun untuk token ini tidak ditemukan.")
