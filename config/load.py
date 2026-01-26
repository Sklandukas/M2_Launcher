import json
import os
from .models import CameraDefaults

def load_camera_defaults(path: str) -> CameraDefaults:
    if not os.path.exists(path):
        return CameraDefaults()

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    s = raw.get("CameraDefaultSettings", {}) or {}

    base = CameraDefaults()
    data = {}
    for k in base.__dict__.keys():
        data[k] = s.get(k, getattr(base, k))

    return CameraDefaults(**data)
