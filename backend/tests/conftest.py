"""Shared fixtures.

Tests run against a real PostgreSQL database (TEST_DATABASE_URL). The schema
is created by running the Alembic migrations, so the migrations are tested
too. Redis is an in-process fake unless TEST_REDIS_URL points at a server.
"""
from __future__ import annotations

import os
from datetime import timedelta

import pytest
from flask_jwt_extended import create_access_token
from sqlalchemy import text

os.environ.setdefault("APP_ENV", "testing")

from citysight import create_app  # noqa: E402
from citysight.auth.passwords import hash_password  # noqa: E402
from citysight.extensions import db  # noqa: E402
from citysight.models import Camera, User  # noqa: E402
from citysight.pipeline.detector import set_detector  # noqa: E402
from citysight.redis_client import get_redis, reset_clients  # noqa: E402

ADMIN_PASSWORD = "Admin-pass-123"
OPERATOR_PASSWORD = "Operator-pass-123"


@pytest.fixture(scope="session")
def app():
    app = create_app("testing", {"SSE_MAX_SECONDS": 3})
    with app.app_context():
        db.session.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        db.session.commit()
        from flask_migrate import upgrade

        upgrade()
    yield app


@pytest.fixture(autouse=True)
def _clean(app):
    with app.app_context():
        db.session.execute(text(
            "TRUNCATE hourly_stats, detections, cameras, users RESTART IDENTITY CASCADE"
        ))
        db.session.commit()
        get_redis(app.config["REDIS_URL"]).flushdb()
    set_detector(None)
    yield
    with app.app_context():
        db.session.remove()
    set_detector(None)


@pytest.fixture
def ctx(app):
    with app.app_context():
        yield


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def redis_client(app):
    return get_redis(app.config["REDIS_URL"])


def _user(username, role, password):
    user = User(username=username, email=f"{username}@example.test", role=role,
                password_hash=hash_password(password))
    db.session.add(user)
    db.session.commit()
    return user.id


@pytest.fixture
def users(app):
    with app.app_context():
        return {
            "admin": _user("admin", "admin", ADMIN_PASSWORD),
            "operator": _user("operator", "operator", OPERATOR_PASSWORD),
        }


@pytest.fixture
def tokens(app, users):
    with app.app_context():
        return {
            role: create_access_token(identity=db.session.get(User, user_id))
            for role, user_id in users.items()
        }


@pytest.fixture
def admin_headers(tokens):
    return {"Authorization": f"Bearer {tokens['admin']}"}


@pytest.fixture
def operator_headers(tokens):
    return {"Authorization": f"Bearer {tokens['operator']}"}


@pytest.fixture
def make_camera(app):
    def _make(name="Simpang Tugu Adipura", status="active", url="rtsp://cctv.example.test/stream1", **extra):
        with app.app_context():
            camera = Camera(name=name, location=extra.pop("location", "Bandar Lampung"),
                            stream_url=url, status=status, **extra)
            db.session.add(camera)
            db.session.commit()
            return camera.id

    return _make


@pytest.fixture
def expired_token(app, users):
    with app.app_context():
        user = db.session.get(User, users["operator"])
        return create_access_token(identity=user, expires_delta=timedelta(seconds=-10))


def pytest_sessionfinish(session, exitstatus):
    reset_clients()
