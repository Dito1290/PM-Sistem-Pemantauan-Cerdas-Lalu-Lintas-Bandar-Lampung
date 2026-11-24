"""Test doubles. These replace YOLO and video sources; they are NOT real CCTV tests."""
from __future__ import annotations

import threading

COCO_NAMES = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck", 9: "traffic light"}


class _List(list):
    def tolist(self):
        return list(self)


class _Boxes:
    def __init__(self, detections):
        self.cls = _List(d[0] for d in detections)
        self.conf = _List(d[1] for d in detections)
        # Relative boxes like Ultralytics' xyxyn: given as a third element, or one
        # fixed, non-overlapping box per detection.
        self.xyxyn = _List(d[2] if len(d) > 2 else [0.1 * i, 0.2, 0.1 * i + 0.05, 0.3]
                           for i, d in enumerate(detections))

    def __len__(self):
        return len(self.cls)


class _Result:
    def __init__(self, detections):
        self.boxes = _Boxes(detections)


class FakeYolo:
    """Mimics the subset of ultralytics.YOLO used by VehicleDetector."""

    def __init__(self, detections=(), names=None):
        self.names = names or COCO_NAMES
        self.detections = list(detections)  # [(class_id, confidence[, [x1, y1, x2, y2]])]
        self.calls = []

    def predict(self, frame, **kwargs):
        self.calls.append(kwargs)
        allowed = set(kwargs.get("classes") or self.names)
        kept = [d for d in self.detections if d[0] in allowed and d[1] >= kwargs.get("conf", 0)]
        return [_Result(kept)]


class FakeCapture:
    """Scripted cv2.VideoCapture replacement.

    ``frames`` = number of frames delivered before the stream "drops";
    None means endless.
    """

    def __init__(self, opened=True, frames=None, frame=b"frame"):
        self.opened = opened
        self.remaining = frames
        self.frame = frame
        self.released = False

    def isOpened(self):
        return self.opened

    def grab(self):
        if self.remaining is None:
            return True
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True

    def retrieve(self):
        return True, self.frame

    def get(self, prop):
        return 0

    def set(self, prop, value):
        return False

    def release(self):
        self.released = True


class ScriptedFactory:
    """Returns a sequence of FakeCaptures, one per (re)connect attempt."""

    def __init__(self, captures):
        self.captures = list(captures)
        self.attempts = 0
        self.lock = threading.Lock()

    def __call__(self, url, settings):
        with self.lock:
            self.attempts += 1
            if self.captures:
                return self.captures.pop(0)
            return FakeCapture(opened=False)
