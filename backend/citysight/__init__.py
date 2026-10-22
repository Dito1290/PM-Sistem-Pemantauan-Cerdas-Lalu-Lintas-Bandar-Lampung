"""CitySight Bandar Lampung backend (Flask application factory)."""
from __future__ import annotations

import logging
import time
import uuid

from flask import Flask, g, request
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import get_config, validate_config
from .extensions import cors, db, jwt, migrate
from .logging_config import configure_logging

log = logging.getLogger("citysight.http")


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))
    if overrides:
        app.config.update(overrides)
    validate_config(app.config)
    app.json.sort_keys = False  # keep documented field order in responses
    configure_logging(app.config["LOG_LEVEL"], app.config["LOG_DIR"])

    trusted_proxies = int(app.config.get("TRUSTED_PROXY_COUNT", 0) or 0)
    if trusted_proxies:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=trusted_proxies, x_proto=trusted_proxies)

    db.init_app(app)
    migrate.init_app(app, db, directory=str(_migrations_dir()))
    jwt.init_app(app)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["FRONTEND_ORIGINS"]}},
        allow_headers=["Authorization", "Content-Type"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        max_age=600,
    )

    from . import models  # noqa: F401  (register models for migrations)
    from .api import cameras, health, stats, stream
    from .auth import routes as auth_routes
    from .auth.tokens import init_jwt
    from .celery_app import init_celery
    from .cli import register_cli
    from .errors import register_error_handlers

    init_jwt(app)
    for blueprint in (auth_routes.bp, cameras.bp, stats.bp, stream.bp, health.bp):
        app.register_blueprint(blueprint)
    register_error_handlers(app)
    register_cli(app)
    init_celery(app)
    _register_request_hooks(app)
    return app


def _migrations_dir():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent / "migrations"


def _register_request_hooks(app: Flask) -> None:
    @app.before_request
    def _start():
        g.request_id = request.headers.get("X-Request-ID", "")[:64] or uuid.uuid4().hex[:16]
        g.started = time.perf_counter()

    @app.after_request
    def _finish(response):
        response.headers["X-Request-ID"] = g.get("request_id", "")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.path.startswith("/api/") and response.mimetype == "application/json":
            response.headers.setdefault("Cache-Control", "no-store")
        if request.path != "/api/health":
            elapsed = (time.perf_counter() - g.get("started", time.perf_counter())) * 1000
            log.info("%s %s -> %s %.1fms [req=%s]", request.method, request.path,
                     response.status_code, elapsed, g.get("request_id"))
        return response
