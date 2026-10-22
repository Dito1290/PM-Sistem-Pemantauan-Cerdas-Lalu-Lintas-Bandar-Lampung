"""Logging setup: console always, plus a daily-rotated file when LOG_DIR is set."""
from __future__ import annotations

import logging
import logging.handlers
import os

FORMAT = "%(asctime)s %(levelname)s [%(process)d:%(threadName)s] %(name)s: %(message)s"


def configure_logging(level: str = "INFO", log_dir: str = "", filename: str = "citysight.log") -> None:
    root = logging.getLogger()
    if getattr(root, "_citysight_configured", False):
        return
    root.setLevel(level.upper())
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(console)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        rotating = logging.handlers.TimedRotatingFileHandler(
            os.path.join(log_dir, filename), when="midnight", backupCount=14, utc=True
        )
        rotating.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(rotating)
    root._citysight_configured = True  # type: ignore[attr-defined]
