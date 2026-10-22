"""Application configuration loaded from environment variables.

Every tunable that the proposal lists (frame rate, confidence, IoU, queue size,
reconnect delay, ...) lives here so it can be changed without editing code.
Secrets have no usable defaults: the app refuses to start in production mode
without them.
"""
from __future__ import annotations

import json
import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class Config:
    ENV_NAME = "base"
    TESTING = False

    # --- Secrets ---------------------------------------------------------
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")

    # --- Database --------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://citysight@127.0.0.1:5432/citysight"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # --- Redis / Celery --------------------------------------------------
    REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND") or None

    # --- Auth ------------------------------------------------------------
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=_int("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", 60))
    JWT_TOKEN_LOCATION = ["headers", "query_string"]
    JWT_QUERY_STRING_NAME = "access_token"
    JWT_ERROR_MESSAGE_KEY = "message"
    BCRYPT_ROUNDS = _int("BCRYPT_ROUNDS", 12)
    LOGIN_MAX_ATTEMPTS = _int("LOGIN_MAX_ATTEMPTS", 5)
    LOGIN_LOCKOUT_SECONDS = _int("LOGIN_LOCKOUT_SECONDS", 900)

    # --- HTTP ------------------------------------------------------------
    FRONTEND_ORIGINS = _list("FRONTEND_ORIGINS", "http://localhost:5173")
    TRUSTED_PROXY_COUNT = _int("TRUSTED_PROXY_COUNT", 0)
    MAX_CONTENT_LENGTH = 64 * 1024

    # --- Video pipeline (proposal Bab 5.2.1 c/d, Tabel 20) ---------------
    MAX_ACTIVE_CAMERAS = _int("MAX_ACTIVE_CAMERAS", 3)
    FRAME_INTERVAL_SECONDS = _float("FRAME_INTERVAL_SECONDS", 0.2)
    FRAME_QUEUE_MAX = _int("FRAME_QUEUE_MAX", 10)
    FRAME_MAX_AGE_SECONDS = _float("FRAME_MAX_AGE_SECONDS", 5.0)
    JPEG_QUALITY = _int("JPEG_QUALITY", 80)
    STREAM_RECONNECT_DELAY_SECONDS = _float("STREAM_RECONNECT_DELAY_SECONDS", 5.0)
    STREAM_OPEN_TIMEOUT_MS = _int("STREAM_OPEN_TIMEOUT_MS", 10000)
    STREAM_READ_TIMEOUT_MS = _int("STREAM_READ_TIMEOUT_MS", 10000)
    CAMERA_SYNC_INTERVAL_SECONDS = _float("CAMERA_SYNC_INTERVAL_SECONDS", 10.0)
    STREAM_ALLOWED_SCHEMES = _list("STREAM_ALLOWED_SCHEMES", "rtsp,rtsps,http,https")
    # Optional host allowlist; empty means any host for the allowed schemes.
    STREAM_ALLOWED_HOSTS = _list("STREAM_ALLOWED_HOSTS", "")
    # Local video files are only for the proposal's "sumber cadangan" testing.
    ALLOW_FILE_SOURCES = _bool("ALLOW_FILE_SOURCES", False)

    # --- YOLO ------------------------------------------------------------
    # No default weights ship with the repo; the variant (YOLOv8n / YOLO11n /
    # YOLO26n) is chosen after tests AI-01 and PT-01 (proposal Tabel 20).
    YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "models/yolo.pt")
    YOLO_CONFIDENCE = _float("YOLO_CONFIDENCE", 0.70)
    YOLO_IOU = _float("YOLO_IOU", 0.50)
    YOLO_DEVICE = os.getenv("YOLO_DEVICE", "") or None
    YOLO_IMGSZ = _int("YOLO_IMGSZ", 640)
    # Class-agnostic NMS: overlapping boxes (IoU > YOLO_IOU) count as one
    # object even if labelled car and truck, per proposal Bab 5.2.1 d.
    YOLO_AGNOSTIC_NMS = _bool("YOLO_AGNOSTIC_NMS", True)
    # Maps our categories to the label names in model.names. Override when a
    # custom model uses different names (e.g. {"motorcycle": "motor"}).
    YOLO_CLASS_NAMES = json.loads(
        os.getenv(
            "YOLO_CLASS_NAMES",
            '{"car": "car", "motorcycle": "motorcycle", "bus": "bus", "truck": "truck"}',
        )
    )

    # --- Statistics ------------------------------------------------------
    REPORT_TIMEZONE = os.getenv("REPORT_TIMEZONE", "Asia/Jakarta")
    HOURLY_AGGREGATION_MINUTE = _int("HOURLY_AGGREGATION_MINUTE", 5)
    HOURLY_AGGREGATION_LOOKBACK_HOURS = _int("HOURLY_AGGREGATION_LOOKBACK_HOURS", 2)

    # --- Logging ---------------------------------------------------------
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR = os.getenv("LOG_DIR", "")


class DevelopmentConfig(Config):
    ENV_NAME = "development"


class ProductionConfig(Config):
    ENV_NAME = "production"


class TestingConfig(Config):
    ENV_NAME = "testing"
    TESTING = True
    SECRET_KEY = "test-secret-key-not-for-production-use-0123456789"
    JWT_SECRET_KEY = "test-jwt-secret-not-for-production-use-0123456789"
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "TEST_DATABASE_URL", "postgresql+psycopg://citysight@127.0.0.1:5432/citysight_test"
    )
    REDIS_URL = os.getenv("TEST_REDIS_URL", "fakeredis://")
    CELERY_BROKER_URL = "memory://"
    LOGIN_MAX_ATTEMPTS = 5
    BCRYPT_ROUNDS = 4  # speed only; production default stays 12
    ALLOW_FILE_SOURCES = True


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    name = name or os.getenv("APP_ENV", "development")
    try:
        return CONFIGS[name]
    except KeyError as error:
        raise RuntimeError(f"Unknown APP_ENV '{name}'. Use one of {sorted(CONFIGS)}") from error


def validate_config(config: dict) -> None:
    """Fail fast on unsafe or inconsistent settings."""
    for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
        value = config.get(key) or ""
        if len(value) < 32:
            raise RuntimeError(
                f"{key} must be set to a random value of at least 32 characters "
                "(see .env.example)."
            )
    if not 0 < config["YOLO_CONFIDENCE"] <= 1 or not 0 < config["YOLO_IOU"] <= 1:
        raise RuntimeError("YOLO_CONFIDENCE and YOLO_IOU must be in (0, 1].")
    if not 10 <= config["BCRYPT_ROUNDS"] <= 15 and not config.get("TESTING"):
        raise RuntimeError("BCRYPT_ROUNDS must be between 10 and 15.")
    if config["FRAME_QUEUE_MAX"] < 1:
        raise RuntimeError("FRAME_QUEUE_MAX must be >= 1.")
    if config["FRAME_INTERVAL_SECONDS"] <= 0:
        raise RuntimeError("FRAME_INTERVAL_SECONDS must be > 0.")
    if "*" in config["FRONTEND_ORIGINS"]:
        raise RuntimeError("FRONTEND_ORIGINS must list explicit origins, not '*'.")
    required = {"car", "motorcycle", "bus", "truck"}
    if set(config["YOLO_CLASS_NAMES"]) != required:
        raise RuntimeError(f"YOLO_CLASS_NAMES must define exactly {sorted(required)}.")
