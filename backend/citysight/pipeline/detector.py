"""YOLO vehicle detector.

* The model is loaded once per worker process (or thread) and reused for every frame.
* Weights are never downloaded: the file at YOLO_MODEL_PATH must exist,
  otherwise ``ModelUnavailable`` is raised (Ultralytics would otherwise try to
  fetch well-known names such as ``yolo11n.pt`` from the internet).
* Class ids are resolved from ``model.names`` at load time instead of assuming
  COCO ids, and loading fails if any of car/motorcycle/bus/truck is missing.
* Counts are "vehicles visible in this frame". There is no tracking, so they
  must not be read as the number of unique vehicles passing the camera.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

CATEGORIES = ("car", "motorcycle", "bus", "truck")


class ModelUnavailable(RuntimeError):
    """Weights missing or the ML runtime is not installed."""


class ModelConfigError(RuntimeError):
    """The model's labels do not match the configured vehicle classes."""


@dataclass(frozen=True)
class VehicleCounts:
    car: int = 0
    motorcycle: int = 0
    bus: int = 0
    truck: int = 0

    @property
    def total(self) -> int:
        return self.car + self.motorcycle + self.bus + self.truck


def resolve_class_ids(model_names: dict[int, str] | list[str], wanted: dict[str, str]) -> dict[int, str]:
    """Map model class ids to our categories using label names."""
    if isinstance(model_names, (list, tuple)):
        model_names = dict(enumerate(model_names))
    by_label = {str(label).strip().lower(): int(class_id) for class_id, label in model_names.items()}
    mapping: dict[int, str] = {}
    missing = []
    for category in CATEGORIES:
        label = str(wanted[category]).strip().lower()
        if label not in by_label:
            missing.append(f"{category}->'{wanted[category]}'")
            continue
        mapping[by_label[label]] = category
    if missing:
        available = ", ".join(sorted(by_label))
        raise ModelConfigError(
            f"Model labels missing for {', '.join(missing)}. Available labels: {available}. "
            "Adjust YOLO_CLASS_NAMES."
        )
    return mapping


class VehicleDetector:
    def __init__(self, model: Any, class_names: dict[str, str], *, confidence: float, iou: float,
                 imgsz: int = 640, device: str | None = None, agnostic_nms: bool = True):
        self.model = model
        self.class_map = resolve_class_ids(model.names, class_names)
        self.confidence = confidence
        self.iou = iou
        self.imgsz = imgsz
        self.device = device
        self.agnostic_nms = agnostic_nms
        log.info("Detector ready; class map %s, conf=%.2f iou=%.2f", self.class_map, confidence, iou)

    def detect(self, frame) -> VehicleCounts:
        kwargs = dict(
            conf=self.confidence,
            iou=self.iou,
            imgsz=self.imgsz,
            classes=sorted(self.class_map),
            agnostic_nms=self.agnostic_nms,
            verbose=False,
        )
        if self.device:
            kwargs["device"] = self.device
        result = self.model.predict(frame, **kwargs)[0]
        counts = dict.fromkeys(CATEGORIES, 0)
        boxes = result.boxes
        if boxes is not None and len(boxes):
            class_ids = boxes.cls.tolist()
            scores = boxes.conf.tolist()
            for class_id, score in zip(class_ids, scores):
                category = self.class_map.get(int(class_id))
                # predict() already applies conf; re-check in case a backend ignores it.
                if category and score >= self.confidence:
                    counts[category] += 1
        return VehicleCounts(**counts)


_override: VehicleDetector | None = None
_local = threading.local()


def load_model(path: str) -> Any:
    weights = Path(path)
    if not weights.is_file():
        raise ModelUnavailable(
            f"YOLO weights not found at '{weights}'. Place the chosen model file there "
            "(see docs/DECISIONS.md); automatic download is disabled."
        )
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ModelUnavailable(
            "Ultralytics is not installed. Install backend/requirements-ml.txt on inference workers."
        ) from exc
    return YOLO(str(weights.resolve()))


def get_detector(config) -> VehicleDetector:
    """One model per worker process, or per thread with ``--pool threads``.

    Ultralytics models are not thread-safe, so a model is never shared
    between threads; each thread loads its own copy once and reuses it.
    """
    if _override is not None:
        return _override
    detector = getattr(_local, "detector", None)
    if detector is None:
        model = load_model(config["YOLO_MODEL_PATH"])
        detector = VehicleDetector(
            model,
            config["YOLO_CLASS_NAMES"],
            confidence=config["YOLO_CONFIDENCE"],
            iou=config["YOLO_IOU"],
            imgsz=config["YOLO_IMGSZ"],
            device=config["YOLO_DEVICE"],
            agnostic_nms=config["YOLO_AGNOSTIC_NMS"],
        )
        _local.detector = detector
    return detector


def set_detector(detector: VehicleDetector | None) -> None:
    """Test hook: force every thread to use ``detector`` (None = normal loading)."""
    global _override
    _override = detector
