"""People-on-the-road indication from the live detections of one camera.

After a motorcycle crash the bikes are usually lifted within seconds, but people
run into the lane and stay there; the same happens with crowds, fights or road
blocks. This counts people whose feet (bottom centre of the box) are inside the
camera's road zone (the same zone as the stopped-vehicle check) and reports when
at least ``min_people`` of them **stay around one spot** for ``seconds``.

Normal traffic also puts people on the lane for a while: groups crossing at a
zebra crossing, people walking along a road without pavement, someone getting on
a motorcycle (Seribu Wajah, 2026-11-24). They move on within about 10-20 seconds
or keep walking. After a crash people stay near the casualties for minutes. So
each person is followed from frame to frame by the position of the feet, and only
people who stayed within LINGER_RADIUS body heights of where they were first seen
count; the default duration is 30 seconds.

Riders and passengers are people on the road too. A person is taken as riding
when the bottom centre of the box (seat or feet) lies inside a vehicle box, or
when most of the box is inside one; the rider's upper body sticks out above the
motorcycle, so overlap alone misses most riders (measured on Seribu Wajah:
riders cover 30-70% of their box with the motorcycle's). Pedestrians crossing are in the lane
for a few seconds only and do not last long enough.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

from .stopped_vehicle import MIN_BOX_HEIGHT, in_any

RIDER_OVERLAP = 0.5   # person counts as rider/passenger if this share of its box is inside a vehicle box
# A lingering person must be seen in this share of the frames. People in a group
# hide each other: on a crash video the third person around the casualties was
# seen in only 45-55% of the frames.
MIN_SHARE = 0.4
LINGER_RADIUS = 2.0   # staying within this many body heights of the first position counts as staying
LOST_SECONDS = 3.0    # a person not seen for this long no longer counts as present
FORGET_SECONDS = 10.0  # ... and is forgotten after this long
ASPECT = 16 / 9       # frame width / height, to measure x and y distances alike (Seribu Wajah 1920x1080)
END_SECONDS = 30.0    # see anomaly_service: indication ends this long after the last report


def _covered(person: list[float], vehicle: list[float]) -> float:
    ix = max(0.0, min(person[2], vehicle[2]) - max(person[0], vehicle[0]))
    iy = max(0.0, min(person[3], vehicle[3]) - max(person[1], vehicle[1]))
    area = (person[2] - person[0]) * (person[3] - person[1])
    return ix * iy / area if area > 0 else 0.0


def _rides(person: list[float], vehicle: list[float]) -> bool:
    seat_x, seat_y = (person[0] + person[2]) / 2, person[3]
    on_it = vehicle[0] <= seat_x <= vehicle[2] and vehicle[1] <= seat_y <= vehicle[3] + 0.02
    return on_it or _covered(person, vehicle) >= RIDER_OVERLAP


def people_on_foot(boxes: list[dict], zone,
                   min_height: float = MIN_BOX_HEIGHT) -> list[dict]:
    """People in the zone, close enough to be reliable, who are not riding a vehicle
    or a bicycle."""
    vehicles = [b["box"] for b in boxes if b["category"] != "person"]
    return [
        b for b in boxes
        if b["category"] == "person" and b["box"][3] - b["box"][1] >= min_height
        and in_any(zone, b["box"]) and not any(_rides(b["box"], v) for v in vehicles)
    ]


@dataclass
class _Person:
    x: float          # feet position where first seen
    y: float
    height: float
    first_seen: float
    last_seen: float
    first_frame: int
    hits: int = 1
    box: list[float] | None = None


def _feet(box: list[float]) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, box[3]


class PeopleOnRoadMonitor:
    def __init__(self, min_people: int, seconds: float, min_height: float = MIN_BOX_HEIGHT):
        self.min_people = min_people
        self.min_height = min_height
        self.seconds = seconds
        self.people: list[_Person] = []
        self.frame = 0
        self.last_reported: float = float("-inf")
        self.alert_open = False
        self.lock = threading.Lock()

    def update(self, t: float, boxes: list[dict], zone) -> dict | None:
        """Returns {"people", "boxes", "seconds"} while enough people stay on the road, else None."""
        self.frame += 1
        claimed: set[int] = set()
        for item in people_on_foot(boxes, zone, self.min_height):
            box = item["box"]
            x, y = _feet(box)
            height = box[3] - box[1]
            best, best_d = None, None
            for i, p in enumerate(self.people):
                if i in claimed:
                    continue
                d = (((x - p.x) * ASPECT) ** 2 + (y - p.y) ** 2) ** 0.5 / max(p.height, height)
                if d <= LINGER_RADIUS and (best_d is None or d < best_d):
                    best, best_d = i, d
            if best is None:
                self.people.append(_Person(x, y, height, t, t, self.frame, box=box))
                claimed.add(len(self.people) - 1)
                continue
            p = self.people[best]
            claimed.add(best)
            p.last_seen, p.box, p.hits = t, box, p.hits + 1
        self.people = [p for p in self.people if t - p.last_seen <= FORGET_SECONDS]
        staying = [
            p for p in self.people
            if t - p.first_seen >= self.seconds and t - p.last_seen <= LOST_SECONDS
            and p.hits / (self.frame - p.first_frame + 1) >= MIN_SHARE
        ]
        if len(staying) < self.min_people:
            return None
        self.last_reported = t
        return {"people": len(staying), "boxes": [p.box for p in staying],
                "seconds": round(max(t - p.first_seen for p in staying))}


_monitors: dict[int, PeopleOnRoadMonitor] = {}
_lock = threading.Lock()


def monitor_for(camera_id: int, min_people: int, seconds: float,
                min_height: float = MIN_BOX_HEIGHT) -> tuple[PeopleOnRoadMonitor, bool]:
    """(monitor, created). A new monitor means earlier state was lost (worker restart)."""
    with _lock:
        monitor = _monitors.get(camera_id)
        if monitor is None or (monitor.min_people, monitor.seconds, monitor.min_height) != (
                min_people, seconds, min_height):
            monitor = _monitors[camera_id] = PeopleOnRoadMonitor(min_people, seconds, min_height)
            return monitor, True
        return monitor, False


def reset() -> None:
    """Test hook."""
    with _lock:
        _monitors.clear()
