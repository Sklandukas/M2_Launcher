from dataclasses import dataclass
from config.load_config import load_config

config_path = "camera_config.json"
config = load_config(config_path)
camera_settings = config.get("CameraDefaultSettings", {})


@dataclass
class CameraDefaults:
    width: int = camera_settings.get("width", "")
    height: int = camera_settings.get("height", "")
    exposure_time: float = camera_settings.get("exposure_time", "")
    gain: float = camera_settings.get("gain", "")
    brightness: float = camera_settings.get("brightness", "")
    frame_rate: float = camera_settings.get("frame_rate", "")
    serial_number: str = camera_settings.get("serial_number", "")

@dataclass
class CameraWorkerParams:
    min_shutter_value: float = camera_settings.get("min_shutter_value", "")
    max_shutter_value: float = camera_settings.get("max_shutter_value", "")
    adjustment_factor: float = camera_settings.get("adjustment_factor", "")
    saturation_lower_bound: float = camera_settings.get("saturation_lower_bound", "") 
    saturation_upper_bound: float = camera_settings.get("saturation_upper_bound")
