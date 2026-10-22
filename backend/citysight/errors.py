"""Application exceptions and Flask error handlers.

Handlers never leak tracebacks or driver messages to clients; details are
logged server-side with the request id instead.
"""
from __future__ import annotations

import logging

from flask import Flask, g
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from werkzeug.exceptions import HTTPException
import redis

from .extensions import db
from .responses import fail

log = logging.getLogger(__name__)


class ApiError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, *, details=None, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        if status is not None:
            self.status = status
        if code is not None:
            self.code = code


class NotFound(ApiError):
    status = 404
    code = "not_found"


class Conflict(ApiError):
    status = 409
    code = "conflict"


class Forbidden(ApiError):
    status = 403
    code = "forbidden"


class ServiceUnavailable(ApiError):
    status = 503
    code = "service_unavailable"


def validation_details(error: ValidationError) -> list[dict]:
    return [
        {"field": ".".join(str(p) for p in item["loc"]) or None, "message": item["msg"]}
        for item in error.errors(include_url=False, include_input=False, include_context=False)
    ]


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(error: ApiError):
        return fail(error.status, error.code, error.message, error.details)

    @app.errorhandler(ValidationError)
    def _validation(error: ValidationError):
        return fail(422, "validation_error", "Input tidak valid.", validation_details(error))

    @app.errorhandler(HTTPException)
    def _http(error: HTTPException):
        codes = {
            400: "bad_request", 404: "not_found", 405: "method_not_allowed",
            413: "payload_too_large", 415: "unsupported_media_type",
        }
        return fail(error.code or 500, codes.get(error.code, "http_error"), error.description or error.name)

    @app.errorhandler(OperationalError)
    def _db_down(error: OperationalError):
        db.session.rollback()
        log.error("Database unavailable [req=%s]: %s", g.get("request_id"), error.__class__.__name__)
        return fail(503, "database_unavailable", "Database sedang tidak tersedia.")

    @app.errorhandler(SQLAlchemyError)
    def _db_error(error: SQLAlchemyError):
        db.session.rollback()
        log.exception("Database error [req=%s]", g.get("request_id"))
        return fail(500, "database_error", "Terjadi kesalahan pada database.")

    @app.errorhandler(redis.RedisError)
    def _redis_error(error: redis.RedisError):
        log.error("Redis unavailable [req=%s]: %s", g.get("request_id"), error)
        return fail(503, "cache_unavailable", "Layanan antrean (Redis) sedang tidak tersedia.")

    @app.errorhandler(Exception)
    def _unhandled(error: Exception):
        db.session.rollback()
        log.exception("Unhandled error [req=%s]", g.get("request_id"))
        return fail(500, "internal_error", "Terjadi kesalahan pada server.")
