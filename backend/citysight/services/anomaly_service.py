"""Anomaly indications derived from the stored per-frame counts.

At one frame per camera per minute vehicles cannot be tracked and a crash
itself is never visible. What the data does show is its effect: a road that
stays much fuller than usual, or a camera that stops delivering frames. Both
are raised as indications for the operator, who checks the CCTV and decides.
Rules and defaults: docs/DECISIONS.md section 8.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from ..extensions import db
from ..models import ANOMALY_CAMERA_OFFLINE, ANOMALY_HIGH_DENSITY, Anomaly, Camera
from ..pipeline import camera_state
from ..redis_client import get_redis
from ..timeutil import floor_hour, isoformat, utcnow
from . import notifier
from .realtime import publish_anomaly
from .serializers import anomaly_to_dict

log = logging.getLogger(__name__)
# Fewer completed hours than this is not a usable picture of "usual".
MIN_BASELINE_HOURS = 3

_BASELINE = text("""
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY avg_vehicle)
               FILTER (WHERE extract(hour FROM hour_bucket AT TIME ZONE :tz) = :local_hour) AS same_hour,
           count(*) FILTER (WHERE extract(hour FROM hour_bucket AT TIME ZONE :tz) = :local_hour) AS same_hour_n,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY avg_vehicle) AS all_hours,
           count(*) AS all_hours_n
    FROM hourly_stats
    WHERE camera_id = :camera_id AND hour_bucket >= :since AND hour_bucket < :until
""")

_WINDOW = text("""
    SELECT count(*) AS frames, min(total_vehicle) AS low, max(total_vehicle) AS high,
           min(timestamp) AS first_at
    FROM detections
    WHERE camera_id = :camera_id AND timestamp > :since AND timestamp <= :until
""")

_PREVIOUS_FRAME = text("""
    SELECT max(timestamp) FROM detections WHERE camera_id = :camera_id AND timestamp < :until
""")

_LAST_FRAME = text("""
    SELECT c.id AS camera_id, d.timestamp
    FROM unnest(CAST(:ids AS integer[])) AS c(id)
    CROSS JOIN LATERAL (
        SELECT timestamp FROM detections d WHERE d.camera_id = c.id ORDER BY d.timestamp DESC LIMIT 1
    ) d
""")


# --- high_density -------------------------------------------------------------

def density_baseline(camera_id: int, at: datetime) -> tuple[float, str] | None:
    """Usual vehicles per frame for this camera: (median, "same_hour" | "all_hours").

    Only completed hours before ``at`` count, so a jam in progress does not
    raise its own baseline.
    """
    config = current_app.config
    tz = config["REPORT_TIMEZONE"]
    until = floor_hour(at)
    row = db.session.execute(_BASELINE, {
        "camera_id": camera_id, "tz": tz, "local_hour": at.astimezone(ZoneInfo(tz)).hour,
        "since": until - timedelta(days=config["ANOMALY_BASELINE_DAYS"]), "until": until,
    }).mappings().one()
    if row["same_hour_n"] >= MIN_BASELINE_HOURS:
        return float(row["same_hour"]), "same_hour"
    if row["all_hours_n"] >= MIN_BASELINE_HOURS:
        return float(row["all_hours"]), "all_hours"
    return None


def density_threshold(baseline: float) -> int:
    config = current_app.config
    return max(config["ANOMALY_DENSITY_MIN_VEHICLES"], math.ceil(baseline * config["ANOMALY_DENSITY_RATIO"]))


def evaluate_density(camera_id: int, frame_at: datetime, total_vehicle: int,
                     photo_jpeg: bytes | None = None) -> list[dict]:
    """Run after each stored detection. Returns the anomaly events it emitted."""
    config = current_app.config
    span = timedelta(minutes=config["ANOMALY_DENSITY_WINDOW_MINUTES"])
    events: list[dict] = []
    active = _active(camera_id, ANOMALY_HIGH_DENSITY)
    if active is not None:
        # After a gap longer than the window (system or camera was off) the old
        # indication says nothing about now; close it and judge the road afresh.
        previous = db.session.execute(_PREVIOUS_FRAME, {"camera_id": camera_id, "until": frame_at}).scalar()
        if previous is None or frame_at - previous > span:
            events += _end(active, previous or active.started_at,
                           reason="Pemantauan sempat terhenti, indikasi ditutup.")
            active = None
    window = db.session.execute(_WINDOW, {
        "camera_id": camera_id, "until": frame_at, "since": frame_at - span,
    }).mappings().one()
    enough_frames = window["frames"] >= config["ANOMALY_DENSITY_MIN_FRAMES"]

    if active is not None:
        # End against the threshold that opened it, even if the baseline moved since.
        threshold = active.details["threshold"]
        if enough_frames and window["high"] < threshold:
            return _end(active, frame_at, reason="Jumlah kendaraan kembali normal.")
        if total_vehicle > active.details.get("peak_vehicle", 0):
            active.details = {**active.details, "peak_vehicle": total_vehicle}
            db.session.commit()
        return []

    baseline = density_baseline(camera_id, frame_at)
    if baseline is None:
        return events
    usual, scope = baseline
    threshold = density_threshold(usual)
    if not (enough_frames and window["low"] >= threshold):
        return events
    seen = f"{window['low']}" if window["low"] == window["high"] else f"{window['low']}-{window['high']}"
    message = (f"Kepadatan tidak wajar: {seen} kendaraan per gambar selama "
               f"{window['frames']} gambar berturut-turut, biasanya sekitar {usual:.0f}. "
               "Bisa karena macet, kecelakaan, acara, atau jalan ditutup.")
    details = {
        "usual_vehicle": round(usual, 2),
        "baseline_scope": scope,
        "threshold": threshold,
        "peak_vehicle": int(window["high"]),
        "frames": int(window["frames"]),
    }
    return events + _start(camera_id, ANOMALY_HIGH_DENSITY, window["first_at"], message, details, photo_jpeg)


# --- camera_offline -----------------------------------------------------------

def check_cameras(now: datetime | None = None, allow_start: bool = True) -> list[dict]:
    """Periodic check (Celery Beat, every minute) for cameras without frames.

    ``allow_start=False`` only ends anomalies; the worker uses it right after
    it starts, when no camera has had a chance to deliver a frame yet.
    """
    now = now or utcnow()
    limit = timedelta(minutes=current_app.config["ANOMALY_OFFLINE_MINUTES"])
    cameras = list(db.session.scalars(
        select(Camera).where(Camera.deleted_at.is_(None), Camera.status == "active").order_by(Camera.id)
    ))
    ids = [c.id for c in cameras]
    last_frame = {r.camera_id: r.timestamp for r in db.session.execute(_LAST_FRAME, {"ids": ids})} if ids else {}
    states = camera_state.read_states(get_redis(current_app.config["REDIS_URL"]), ids)
    events: list[dict] = []

    for camera in cameras:
        last = last_frame.get(camera.id)
        # A camera that was just added or re-activated gets the full grace period.
        reference = max(last, camera.updated_at) if last else camera.updated_at
        active = _active(camera.id, ANOMALY_CAMERA_OFFLINE)
        if now - reference < limit:
            if active is not None and last is not None and last > active.started_at:
                events += _end(active, last, reason="Gambar dari kamera masuk lagi.")
            continue
        if active is not None or not allow_start:
            continue
        density = _active(camera.id, ANOMALY_HIGH_DENSITY)
        if density is not None:
            events += _end(density, now, reason="Kamera tidak mengirim gambar, kepadatan tidak bisa dipantau.")
        state = states.get(camera.id, {})
        message = f"Kamera tidak mengirim gambar selama {_duration(now - reference)}. {_offline_cause(state)}"
        details = {
            "last_frame_at": isoformat(last),
            "stream_state": state.get("state"),
            "last_error": state.get("last_error"),
            "last_inference_error": state.get("last_inference_error"),
        }
        events += _start(camera.id, ANOMALY_CAMERA_OFFLINE, reference, message, details)

    # Cameras switched off or deleted on purpose are not anomalies any more.
    stale = db.session.scalars(
        select(Anomaly).where(Anomaly.ended_at.is_(None), Anomaly.camera_id.not_in(ids or [0]))
    )
    for anomaly in list(stale):
        events += _end(anomaly, now, reason="Kamera dinonaktifkan atau dihapus.")
    return events


def _duration(span: timedelta) -> str:
    minutes = int(span.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} menit"
    if minutes < 24 * 60:
        return f"{minutes // 60} jam {minutes % 60} menit"
    return f"{minutes // (24 * 60)} hari {minutes % (24 * 60) // 60} jam"


def _offline_cause(state: dict) -> str:
    stream_state = state.get("state")
    if stream_state in (None, "offline", "unknown"):
        return "Layanan ingest tidak berjalan atau Redis tidak terjangkau."
    if stream_state in ("connecting", "reconnecting"):
        error = state.get("last_error")
        return "Sumber CCTV tidak bisa dibuka" + (f" ({error})." if error else ".")
    if state.get("last_inference_error"):
        return f"Gambar masuk tetapi gagal dideteksi ({state['last_inference_error']})."
    return "Gambar masuk tetapi belum tersimpan; periksa worker deteksi."


# --- shared -------------------------------------------------------------------

def list_anomalies(*, status: str | None, camera_id: int | None, type_: str | None,
                   page: int, per_page: int) -> tuple[list[tuple[Anomaly, str]], int]:
    query = select(Anomaly, Camera.name).join(Camera, Camera.id == Anomaly.camera_id)
    if status == "active":
        query = query.where(Anomaly.ended_at.is_(None))
    elif status == "ended":
        query = query.where(Anomaly.ended_at.is_not(None))
    if camera_id is not None:
        query = query.where(Anomaly.camera_id == camera_id)
    if type_ is not None:
        query = query.where(Anomaly.type == type_)
    total = db.session.scalar(select(db.func.count()).select_from(query.subquery()))
    rows = db.session.execute(
        query.order_by(Anomaly.started_at.desc(), Anomaly.id.desc()).limit(per_page).offset((page - 1) * per_page)
    ).all()
    return [(row[0], row[1]) for row in rows], int(total or 0)


def _active(camera_id: int, type_: str) -> Anomaly | None:
    return db.session.scalar(
        select(Anomaly).where(Anomaly.camera_id == camera_id, Anomaly.type == type_, Anomaly.ended_at.is_(None))
    )


def _start(camera_id: int, type_: str, started_at: datetime, message: str, details: dict,
           photo_jpeg: bytes | None = None) -> list[dict]:
    new_id = db.session.execute(
        insert(Anomaly)
        .values(camera_id=camera_id, type=type_, started_at=started_at, message=message, details=details)
        .on_conflict_do_nothing(index_elements=["camera_id", "type"], index_where=text("ended_at IS NULL"))
        .returning(Anomaly.id)
    ).scalar()
    db.session.commit()
    if new_id is None:  # another task opened it first
        return []
    anomaly = db.session.get(Anomaly, new_id)
    log.warning("Camera %s: anomaly %s started: %s", camera_id, type_, message)
    return [_announce(anomaly, "started", photo_jpeg)]


def _end(anomaly: Anomaly, ended_at: datetime, reason: str) -> list[dict]:
    anomaly.ended_at = max(ended_at, anomaly.started_at)
    anomaly.details = {**anomaly.details, "end_reason": reason}
    db.session.commit()
    log.info("Camera %s: anomaly %s ended: %s", anomaly.camera_id, anomaly.type, reason)
    return [_announce(anomaly, "ended")]


def _announce(anomaly: Anomaly, change: str, photo_jpeg: bytes | None = None) -> dict:
    camera = db.session.get(Camera, anomaly.camera_id)
    event = {"change": change, **anomaly_to_dict(anomaly, camera.name if camera else None)}
    config = current_app.config
    publish_anomaly(get_redis(config["REDIS_URL"]), event)
    if notifier.telegram_enabled(config):
        notifier.send_telegram(config, _telegram_text(anomaly, camera, change), photo_jpeg)
    return event


_LABELS = {ANOMALY_HIGH_DENSITY: "Kepadatan tidak wajar", ANOMALY_CAMERA_OFFLINE: "Kamera tidak mengirim gambar"}


def _telegram_text(anomaly: Anomaly, camera: Camera | None, change: str) -> str:
    tz = ZoneInfo(current_app.config["REPORT_TIMEZONE"])
    where = f"{camera.name} ({camera.location})" if camera else f"kamera {anomaly.camera_id}"
    started = anomaly.started_at.astimezone(tz).strftime("%d-%m-%Y %H:%M")
    if change == "started":
        return (f"INDIKASI ANOMALI - {_LABELS[anomaly.type]}\n"
                f"Kamera: {where}\nMulai: {started} WIB\n\n{anomaly.message}\n\n"
                "Ini indikasi otomatis, mohon cek CCTV untuk memastikan.")
    minutes = round((anomaly.ended_at - anomaly.started_at).total_seconds() / 60)
    return (f"SELESAI - {_LABELS[anomaly.type]}\nKamera: {where}\n"
            f"Mulai {started} WIB, berlangsung sekitar {minutes} menit.\n"
            f"{anomaly.details.get('end_reason', '')}")
