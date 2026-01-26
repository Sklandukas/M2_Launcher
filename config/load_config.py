import os
import json


def load_config(filename):
    if not os.path.exists(filename):
        default_config = {"CameraDefaultSettings": {
            "width": 1288,
            "height": 964,
            "exposure_time": 1000,
            "gain": 0,
            "brightness": 1.367188,
            "frame_rate": 30,
            "serial_number": ""
        }}
        print(f"Config file {filename} not found, using defaults: {json.dumps(default_config, indent=2)}")
        return default_config

    with open(filename, "r") as f:
        config = json.load(f)
        print(f"Loaded config from {filename}: {json.dumps(config, indent=2)}")
        return config