# YOLO weights

Place the chosen weights file here (default path `models/yolo.pt`, configurable
with `YOLO_MODEL_PATH`). Weights are not committed and are **never downloaded
automatically** by the backend.

Proposal Tabel 20 candidates: YOLOv8n, YOLO11n, YOLO26n (COCO, not retrained).
Obtain the file from the official Ultralytics release you choose, verify its
checksum, and record the exact file + version in docs/DECISIONS.md.

On load, the worker checks that `model.names` contains `car`, `motorcycle`,
`bus` and `truck` (or the labels configured in `YOLO_CLASS_NAMES`).
