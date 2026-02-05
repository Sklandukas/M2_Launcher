import os
import time
import threading
import traceback
import tkinter.messagebox as messagebox

from devices.device_maneger import DeviceManager
from config.load import load_camera_defaults
from config.models import CameraWorkerParams

from devices.camera.camera_service import CameraService
from devices.axis.axis_service import AxisService
from devices.laser.laser_service import LaserService

from measurement.measurement_service import MeasurementService
from storage.storage_service import StorageService
from storage.converter import _save_data
from measurement.focus import generate_track_by_focus


def _norm_name(x) -> str:
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def build_track_positions(track, step_size: int, max_length: int):
    if not track:
        return []

    vals = []
    for t in track:
        try:
            v = float(str(t).strip())
            vals.append(v)
        except Exception:
            continue

    if not vals:
        return []

    max_idx_like = (max_length // step_size) + 2
    looks_like_positions = any(v > max_idx_like for v in vals)

    positions = []
    if looks_like_positions:
        for v in vals:
            pos = int(round(v))
            if 0 <= pos <= max_length:
                positions.append(pos)
    else:
        for v in vals:
            idx = int(round(v))
            pos = idx * step_size
            if 0 <= pos <= max_length:
                positions.append(pos)

    positions = sorted(set(positions))
    return positions


def prune_files_not_in_track(track_positions, raw_dir, pgm_dir):
    keep_idx = {str(int(round(p))) for p in track_positions}  

def prune_everything(track_positions, step_size, raw_dir, pgm_dir, images_dict, z_list, dx_list, dy_list):
    if not track_positions:
        return

    keep_idx = {str(int(round(p / step_size))) for p in track_positions}

    for d in (raw_dir, pgm_dir):
        if not d or not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            path = os.path.join(d, fn)
            if not os.path.isfile(path):
                continue
            stem, _ext = os.path.splitext(fn)
            stem_n = _norm_name(stem)
            if stem_n not in keep_idx:
                try:
                    os.remove(path)
                except Exception:
                    pass

    if images_dict is not None:
        for k in list(images_dict.keys()):
            if _norm_name(k) not in keep_idx:
                images_dict.pop(k, None)

    new_z, new_dx, new_dy = [], [], []
    for z, dx, dy in zip(z_list, dx_list, dy_list):
        if _norm_name(z) in keep_idx:
            new_z.append(z)
            new_dx.append(dx)
            new_dy.append(dy)

    z_list[:] = new_z
    dx_list[:] = new_dx
    dy_list[:] = new_dy


class CameraWorker:
    def __init__(self, config_path="camera_config.json"):
        self.camera_defaults = load_camera_defaults(config_path)
        self.params = CameraWorkerParams()

        self.serial_number = self.camera_defaults.serial_number

        self.wavelength = None
        self.model = None
        self.serial = None

        self.images_dict = {}

        self.stop_event = threading.Event()

        self.camera_service = CameraService(serial_number=self.serial_number)
        self.cam = None

        base_dir = os.path.dirname(os.path.abspath(__file__))
        setings_path = os.path.join(base_dir, "config", "setting.json")
        self.device_manager = DeviceManager(config_path=setings_path)

        self.axis_service = AxisService(self.device_manager)
        self.axis_controller = None
        self.axis_connected = False

        self.laser_service = None
        self.stop_requested = False
        self.process_running = False

        self.measure = MeasurementService(self)
        self.storage = StorageService(self)

        self.laser_button = None

        print("CameraWorker ready.")
        print("Defaults:", self.camera_defaults)

    def toggle_laser(self):
        if not self.axis_connected or self.axis_controller is None:
            messagebox.showerror("Laser controller error", "Pirma prijunkite ašį (axis_controller).")
            return

        if self.laser_service is None:
            self.laser_service = LaserService(self.axis_controller)

        if self.laser_service.laser_on:
            return

        try:
            self.laser_service.turn_on()
            info, serial, model, wavelength = self.laser_service.get_laser_info()

            if serial:
                self.serial = serial
            if model:
                self.model = model
            if wavelength:
                self.wavelength = wavelength

            if self.laser_button:
                self.laser_button.config(text="Turn OFF Laser", bg="red")

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Laser controller error", f"Unable to control the laser: {e}")

    def capture_save_measure(self, position, idx, raw_dir, pgm_dir):
        img = self.capture_image(position)
        if img is None:
            return None, None

        filename = str(int(idx))
        self.images_dict[filename] = img.copy()
        _save_data(self, raw_dir, pgm_dir, img, filename, position, position)

        res = self.beam(img)
        return img, res

    def start_processs(self):
        if not self.axis_connected or self.axis_controller is None:
            messagebox.showerror("Error", "Axis controller is not connected.")
            return
        if self.cam is None:
            messagebox.showerror("Error", "Camera is not connected.")
            return

        self.toggle_laser()

        self.process_running = True
        self.stop_requested = False
        self.stop_event.clear()
        self.images_dict.clear()

        folder_name = f"M2_Data_{self.serial}_{self.model}_{time.strftime('%Y-%m-%d_%H-%M-%S')}"
        raw_dir = os.path.join(folder_name, "raw")
        pgm_dir = os.path.join(folder_name, "pgm")
        analysis_dir = os.path.join(folder_name, "analysis")
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(pgm_dir, exist_ok=True)
        os.makedirs(analysis_dir, exist_ok=True)

        max_length = self.get_from_settings_json("length_of_runners")
        step_size = 1587

        z_list, dx_list, dy_list = [], [], []

        current = 0
        prev_area = None
        inc_count = 0

        track_positions = None  

        while current <= max_length and not self.stop_event.is_set():
            self.axis_service.go_to(axis_no=0, position=current)

            idx = int(round(current / step_size))
            img, res = self.capture_save_measure(current, idx, raw_dir, pgm_dir)

            if res is None:
                current += step_size
                continue

            dx = res.Dx_mm
            dy = res.Dy_mm

            z_list.append(str(idx))
            dx_list.append(dx)
            dy_list.append(dy)

            area = dx * dy
            if prev_area is not None and area > prev_area:
                inc_count += 1
            else:
                inc_count = 0

            prev_area = area

            if inc_count >= 5:
                raw_track = generate_track_by_focus(current/step_size, max_length, step_size)
                track_positions = build_track_positions(raw_track, step_size, max_length)

                prune_everything(
                    track_positions=track_positions,
                    step_size=step_size,
                    raw_dir=raw_dir,
                    pgm_dir=pgm_dir,
                    images_dict=self.images_dict,
                    z_list=z_list,
                    dx_list=dx_list,
                    dy_list=dy_list
                )

                break

            current += step_size

        if not track_positions or self.stop_event.is_set():
            return

        measured_idx = {int(_norm_name(z)) for z in z_list}  
        for pos in track_positions:
            if self.stop_event.is_set():
                break

            idx = int(round(pos / step_size))
            if idx in measured_idx:
                continue

            self.axis_service.go_to(axis_no=0, position=pos)

            img, res = self.capture_save_measure(pos, idx, raw_dir, pgm_dir)
            if res is None:
                continue

            dx = res.Dx_mm
            dy = res.Dy_mm

            z_list.append(str(idx))
            dx_list.append(dx)
            dy_list.append(dy)
            measured_idx.add(idx)

