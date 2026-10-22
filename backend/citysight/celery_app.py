"""Celery application bound to the Flask app context.

Worker:  celery -A celery_worker.celery worker -Q detection,stats -l info
Beat:    celery -A celery_worker.celery beat -l info
"""
from __future__ import annotations

from celery import Celery, Task
from celery.schedules import crontab
from flask import Flask


class FlaskTask(Task):
    """Runs every task inside the Flask app context.

    Defined at module level: the prefork pool may use the "spawn" start
    method (default on macOS), which must be able to pickle the task class.
    """

    def __call__(self, *args, **kwargs):
        with self.app.flask_app.app_context():
            return self.run(*args, **kwargs)


def init_celery(app: Flask) -> Celery:
    celery = Celery(app.import_name, task_cls=FlaskTask)
    celery.flask_app = app
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        task_ignore_result=True,
        task_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        worker_prefetch_multiplier=1,
        task_routes={
            "citysight.detect_latest_frame": {"queue": "detection"},
            "citysight.aggregate_hourly_stats": {"queue": "stats"},
        },
        beat_schedule={
            "aggregate-hourly-stats": {
                "task": "citysight.aggregate_hourly_stats",
                "schedule": crontab(minute=app.config["HOURLY_AGGREGATION_MINUTE"]),
                "options": {"queue": "stats", "expires": 3000},
            },
        },
        broker_connection_retry_on_startup=True,
    )
    celery.set_default()
    app.extensions["celery"] = celery
    from .tasks import detection, stats  # noqa: F401  (register tasks)

    return celery

