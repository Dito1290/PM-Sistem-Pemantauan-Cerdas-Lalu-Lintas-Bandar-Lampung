"""Stopped-vehicle indication from the live detections of one camera.

A vehicle that does not move keeps its box in the same place from frame to
frame, so no tracker is needed: every box inside the camera's road zone is
matched against the boxes seen before (IoU with the box where it first
stopped). A box that keeps matching for ``stop_seconds``, in at least
MIN_PRESENCE of the frames (so a busy spot that many vehicles drive over does
not count), while other vehicles in the zone are moving, is reported. Queues at a red light are not reported
because nothing in the zone is moving then, and jams or pick-up crowds are not
reported because several vehicles stand still together (QUEUE_MIN_VEHICLES).

Zones (``ANOMALY_ZONES_FILE``, JSON ``{"<camera_id>": [[x, y], ...]}`` with
coordinates relative to the frame, 0..1) cover only the lanes where traffic
should keep moving: no shoulders, parking spaces or angkot stops. A camera may
have several areas, ``{"<camera_id>": [[[x, y], ...], [[x, y], ...]]}``, one per
traffic direction: "other traffic is moving" is then judged within the area of
the stopped vehicle, so a queue in one direction is not reported because the
opposite direction flows (seen on camera 1, 2026-11-24). A camera can also
switch checks off where stopping is normal (fuel queue, parking, school
pick-up): ``{"<camera_id>": {"areas": [...], "disabled": ["stopped_vehicle"]}}``,
or only at certain local hours: ``"disabled_hours": {"stopped_vehicle": ["18:00-06:00"]}``
(night-time hangouts with parked motorcycles at camera 2, 2026-11-24). A camera
without a zone is not checked. PTZ cameras that turn or zoom move the road
away from the zone; that is a known limitation of this first version.

State lives in the worker process; each camera is processed by one task at a
time (detection slot), so a lock per camera is enough.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

MATCH_IOU = 0.5           # same place if the box overlaps its first stopped box this much
FORGET_SECONDS = 20.0     # a stopped vehicle hidden behind passing traffic is kept this long
MOVING_RECENT_SECONDS = 30.0  # "traffic is flowing" = a moving vehicle seen in the zone this recently
MOVING_MAX_AGE = 3.0      # a box seen in place for less than this counts as moving traffic
# A stopped vehicle is in (almost) every frame; a spot that different vehicles
# keep driving over is filled only now and then. Below this share it is traffic.
MIN_PRESENCE = 0.7
# Boxes lower than this share of the frame height are far away: detections flicker
# and different vehicles look like one, so they are ignored by the live checks.
MIN_BOX_HEIGHT = 0.06
# A breakdown or crash leaves one or two vehicles standing while traffic passes.
# When a standing vehicle has neighbours that have also stood still for
# QUEUE_SECONDS, so that QUEUE_MIN_VEHICLES stand together, it is a jam, a queue,
# a row of parked or pick-up vehicles (camera 1, 2026-11-24): not reported.
# Neighbours outside the zone count too: a pick-up row along the kerb is mostly
# outside it, with only its end inside.
QUEUE_MIN_VEHICLES = 3
QUEUE_SECONDS = 30.0
OUTSIDE = -1  # area of a vehicle tracked only as a possible neighbour


def iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def as_areas(zone) -> list[list[list[float]]]:
    """A single polygon or a list of polygons -> list of polygons."""
    if not zone:
        return []
    return [zone] if isinstance(zone[0][0], (int, float)) else zone


def _near(a: list[float], b: list[float]) -> bool:
    """b overlaps a grown by its own width and height on every side."""
    w, h = a[2] - a[0], a[3] - a[1]
    return a[0] - w < b[2] and b[0] < a[2] + w and a[1] - h < b[3] and b[1] < a[3] + h


def area_of(areas: list[list[list[float]]], box: list[float]) -> int | None:
    for i, polygon in enumerate(areas):
        if in_zone(polygon, box):
            return i
    return None


def in_any(zone, box: list[float]) -> bool:
    return area_of(as_areas(zone), box) is not None


def in_zone(zone: list[list[float]], box: list[float]) -> bool:
    """The bottom centre of the box (where the wheels touch the road) decides.

    A vehicle cut off by the bottom of the frame has its bottom exactly on the
    frame edge, where a zone drawn to the edge ends; nudge it just inside.
    """
    x, y = (box[0] + box[2]) / 2, min(box[3], 0.999)
    inside = False
    j = len(zone) - 1
    for i in range(len(zone)):
        xi, yi = zone[i]
        xj, yj = zone[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


@dataclass
class _Candidate:
    anchor: list[float]
    category: str
    first_seen: float
    last_seen: float
    box: list[float] = field(default_factory=list)
    first_frame: int = 0
    hits: int = 1
    area: int = 0

    def stopped_for(self) -> float:
        return self.last_seen - self.first_seen

    def presence(self, frame: int) -> float:
        return self.hits / (frame - self.first_frame + 1)


class StoppedVehicleMonitor:
    """Per-camera state. ``update`` returns the vehicles that count as stopped now."""

    def __init__(self, stop_seconds: float, min_height: float = MIN_BOX_HEIGHT):
        self.min_height = min_height
        self.stop_seconds = stop_seconds
        self.candidates: list[_Candidate] = []
        self.last_moving: dict[int, float] = {}
        self.frame = 0
        self.last_reported: float = float("-inf")
        self.alert_open = False
        self.lock = threading.Lock()

    def update(self, t: float, boxes: list[dict], zone) -> list[dict]:
        """``zone`` is one polygon or a list of polygons (one per traffic direction)."""
        areas = as_areas(zone)
        self.frame += 1
        in_road = []
        for b in boxes:
            if b["box"][3] - b["box"][1] < self.min_height:
                continue
            area = area_of(areas, b["box"])
            in_road.append((OUTSIDE if area is None else area, b))
        claimed: set[int] = set()
        for area, item in in_road:
            best, best_iou = None, MATCH_IOU
            for i, cand in enumerate(self.candidates):
                if i in claimed:
                    continue
                score = iou(cand.anchor, item["box"])
                if score >= best_iou:
                    best, best_iou = i, score
            if best is None:
                self.candidates.append(_Candidate(item["box"], item["category"], t, t, item["box"], self.frame,
                                                  area=area))
                claimed.add(len(self.candidates) - 1)
                if area != OUTSIDE:
                    self.last_moving[area] = t
                continue
            cand = self.candidates[best]
            claimed.add(best)
            # Recompute the area every frame: the zones file can change while a
            # vehicle stands (a parked scooter stayed reported for 14 minutes
            # after its spot was taken out of the zone, 2026-11-24).
            cand.last_seen, cand.box, cand.area = t, item["box"], area
            cand.hits += 1
            if cand.stopped_for() < MOVING_MAX_AGE and area != OUTSIDE:
                self.last_moving[area] = t
        self.candidates = [c for c in self.candidates if t - c.last_seen <= FORGET_SECONDS]

        standing = [c for c in self.candidates
                    if c.stopped_for() >= QUEUE_SECONDS and c.presence(self.frame) >= MIN_PRESENCE]

        # Group standing vehicles that touch each other in a chain (a row along the
        # kerb, a queue): the end of a long row has only one direct neighbour.
        group = list(range(len(standing)))

        def root(i: int) -> int:
            while group[i] != i:
                group[i] = group[group[i]]
                i = group[i]
            return i

        for i in range(len(standing)):
            for j in range(i + 1, len(standing)):
                if _near(standing[i].box, standing[j].box) or _near(standing[j].box, standing[i].box):
                    group[root(i)] = root(j)
        size: dict[int, int] = {}
        for i in range(len(standing)):
            size[root(i)] = size.get(root(i), 0) + 1
        in_row = {id(c) for i, c in enumerate(standing) if size[root(i)] >= QUEUE_MIN_VEHICLES}

        def stands_alone(c: _Candidate) -> bool:
            return id(c) not in in_row

        # Only vehicles inside the zone, where traffic in the same area (direction)
        # is flowing (a queue at a red light has nothing moving around it) and
        # that do not stand in a row with others (jam, parking, pick-up).
        stopped = [
            {"category": c.category, "box": c.box, "stopped_seconds": round(c.stopped_for())}
            for c in self.candidates
            if c.area != OUTSIDE
            and c.stopped_for() >= self.stop_seconds and c.presence(self.frame) >= MIN_PRESENCE
            and t - self.last_moving.get(c.area, float("-inf")) <= MOVING_RECENT_SECONDS
            and stands_alone(c)
        ]
        if stopped:
            self.last_reported = t
        return stopped


class Zones:
    """Road zones per camera, re-read when the file changes."""

    def __init__(self, path: str):
        self.path = path
        self._mtime: float | None = None
        self._zones: dict[int, list[list[float]]] = {}
        self._disabled: dict[int, set[str]] = {}
        self._hours: dict[int, dict[str, list[tuple[int, int]]]] = {}

    def disabled(self, camera_id: int, local_time=None) -> set[str]:
        """Checks switched off for this camera, always or at ``local_time`` (a datetime.time
        in REPORT_TIMEZONE). Read with the zones."""
        self.get(camera_id)
        off = set(self._disabled.get(camera_id, set()))
        if local_time is not None:
            minute = local_time.hour * 60 + local_time.minute
            for check, spans in self._hours.get(camera_id, {}).items():
                if any(_in_span(minute, start, end) for start, end in spans):
                    off.add(check)
        return off

    def get(self, camera_id: int) -> list[list[list[float]]] | None:
        """The camera's areas (list of polygons), or None without a zone."""
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            self._zones, self._disabled, self._hours, self._mtime = {}, {}, {}, None
            return None
        if mtime != self._mtime:
            self._mtime = mtime
            try:
                with open(self.path, encoding="utf-8") as f:
                    raw = json.load(f)
                zones, disabled, hours = {}, {}, {}
                for k, v in raw.items():
                    if isinstance(v, dict):
                        disabled[int(k)] = set(v.get("disabled", []))
                        hours[int(k)] = {check: [_parse_span(s) for s in spans]
                                         for check, spans in v.get("disabled_hours", {}).items()}
                        v = v.get("areas", [])
                    areas = [[[float(x), float(y)] for x, y in polygon]
                             for polygon in as_areas(v) if len(polygon) >= 3]
                    if areas:
                        zones[int(k)] = areas
                self._zones, self._disabled, self._hours = zones, disabled, hours
                log.info("Loaded road zones for camera(s) %s from %s", sorted(self._zones), self.path)
            except (OSError, ValueError, TypeError) as exc:
                log.error("Cannot read road zones %s: %s", self.path, exc)
                self._zones = {}
        return self._zones.get(camera_id)


def _parse_span(text_: str) -> tuple[int, int]:
    """"18:00-06:00" -> (1080, 360) minutes; the span may run past midnight."""
    start, end = (part.strip() for part in text_.split("-"))
    to_min = lambda hhmm: int(hhmm.split(":")[0]) * 60 + int(hhmm.split(":")[1])  # noqa: E731
    return to_min(start), to_min(end)


def _in_span(minute: int, start: int, end: int) -> bool:
    return start <= minute < end if start <= end else minute >= start or minute < end


_monitors: dict[int, StoppedVehicleMonitor] = {}
_monitors_lock = threading.Lock()
_zones: Zones | None = None


def monitor_for(camera_id: int, stop_seconds: float,
                min_height: float = MIN_BOX_HEIGHT) -> tuple[StoppedVehicleMonitor, bool]:
    """(monitor, created). A new monitor means earlier state was lost (worker restart)."""
    with _monitors_lock:
        monitor = _monitors.get(camera_id)
        if monitor is None or (monitor.stop_seconds, monitor.min_height) != (stop_seconds, min_height):
            monitor = _monitors[camera_id] = StoppedVehicleMonitor(stop_seconds, min_height)
            return monitor, True
        return monitor, False


def zones_from(path: str) -> Zones:
    global _zones
    if _zones is None or _zones.path != path:
        _zones = Zones(path)
    return _zones


def reset() -> None:
    """Test hook."""
    global _zones
    with _monitors_lock:
        _monitors.clear()
    _zones = None
