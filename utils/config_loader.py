import json, os

def load_config(filename: str) -> dict:
    if not os.path.exists(filename):
        return {"CameraDefaultSettings": {...}}
    with open(filename, "r") as f:
        return json.load(f)

def get_from_json(base_dir: str, key: str) -> object:
    json_path = os.path.join(base_dir, "config", "setting.json")
    with open(json_path, "r") as f:
        data = json.load(f)
    return data["CameraDefaultSettings"][key]


