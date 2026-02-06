import os
import time
import json
import cv2
import threading
import traceback
import numpy as np
import bisect
import tkinter as tk
import tkinter.messagebox as messagebox
from tkinter import filedialog
from threading import Thread
from PIL import Image, ImageTk
import matplotlib.backends.backend_agg as backend_agg

from devices.device_maneger import DeviceManager

from devices.camera.camera_settings import set_default_configuration
from utils.json_edit import change_val
from utils.CameraWorkers_utils import camera_worker_task

from config.load import load_camera_defaults
from config.models import CameraWorkerParams
from ui.tk_utils import ui_call
from ui.dialogs import hand_mode_dialog, read_data_folder

from devices.camera.camera_display import prepare_for_tk

from devices.axis.axis_service import AxisService
from devices.laser.laser_service import LaserService
from measurement.focus import find_focus, generate_track_by_focus
from measurement.measurement_service import MeasurementService
from storage.storage_service import StorageService

from measurement.calculations import beam_size_k4_fixed_axes
from measurement.quadrometer import compute_m2_hyperbola
from storage.converter import _save_data

# IMPORTANT: we only use SimpleCameraCapture + FlirCameraConnection (no CameraService)
from devices.camera.camera_service import SimpleCameraCapture
from devices.camera.camera_connection import FlirCameraConnection


DEBUG_TRACK = False


def _norm_name(x) -> str:
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def track_to_step_positions(track, steps_per_mm: int, max_steps: int):
    """
    Accepts either track in mm (floats) or in steps (ints).
    Returns unique sorted step positions [0..max_steps].
    """
    if not track:
        return []

    vals = []
    for t in track:
        try:
            vals.append(float(str(t).strip()))
        except Exception:
            continue

    if not vals:
        return []

    max_mm = max_steps / float(steps_per_mm) if steps_per_mm else 0.0
    mx = max(vals)
    looks_like_mm = mx <= (max_mm + 5.0)

    positions = []
    if looks_like_mm:
        for v in vals:
            pos_steps = int(round(v * steps_per_mm))
            if 0 <= pos_steps <= max_steps:
                positions.append(pos_steps)
    else:
        for v in vals:
            pos_steps = int(round(v))
            if 0 <= pos_steps <= max_steps:
                positions.append(pos_steps)

    return sorted(set(positions))


def prune_everything(track_positions, step_size, raw_dir, pgm_dir, images_dict, measurements):
    """
    Keeps ONLY frames whose idx is in keep_idx, where idx = steps//step_size.
    Also prunes files (raw/pgm) and images_dict keys matching idx strings.
    Finally prunes measurements list so lengths can never mismatch.
    """
    if not track_positions:
        return

    keep_idx = {int(p // step_size) for p in track_positions}

    # prune files by filename stem (idx)
    for d in (raw_dir, pgm_dir):
        if not d or not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            path = os.path.join(d, fn)
            if not os.path.isfile(path):
                continue
            stem, _ext = os.path.splitext(fn)
            try:
                idx = int(float(_norm_name(stem)))
            except Exception:
                continue
            if idx not in keep_idx:
                try:
                    os.remove(path)
                except Exception:
                    pass

    if images_dict is not None:
        for k in list(images_dict.keys()):
            try:
                idx = int(float(_norm_name(k)))
            except Exception:
                continue
            if idx not in keep_idx:
                images_dict.pop(k, None)

    if measurements is not None:
        measurements[:] = [m for m in measurements if m["idx"] in keep_idx]


class CameraWorker:
    def __init__(self, config_path="camera_config.json"):
        # config
        self.config_path = config_path
        self.camera_defaults = load_camera_defaults(config_path)
        self.params = CameraWorkerParams()

        self.serial_number = self.camera_defaults.serial_number

        self.wavelength = None
        self.model = None
        self.serial = None

        self.previous_saturation_level = 0
        self.previous_background_level = 0
        self.last_known_exposure_time = float(self.camera_defaults.exposure_time)

        self.images_dict = {}
        self.latest_frame = None

        self.running = False
        self.worker_thread = None
        self.display_running = False

        self.frame_count = 0
        self.start_time = None

        self.camera_conn = None
        self.cam = None

        base_dir = os.path.dirname(os.path.abspath(__file__))
        settings_path = os.path.join(base_dir, "config", "setting.json")
        self.device_manager = DeviceManager(config_path=settings_path)

        self.axis_service = AxisService(self.device_manager)
        self.axis_controller = None
        self.axis_connected = False

        self.laser_service = None
        self.stop_event = threading.Event()
        self.stop_requested = False
        self.process_running = False

        self.measurement_figure = None
        self.gif_path = None

        self.measure = MeasurementService(self)
        self.storage = StorageService(self)

        self.root = None
        self.axis_button = None
        self.axis_status_label = None
        self.test_button = None
        self.start_button = None
        self.stop_button = None
        self.focus_button = None
        self.handmode_button = None

        self.camera_label = None
        self.figure_button = None
        self.camera_button = None
        self.gif_button = None
        self.laser_button = None
        self.save_data_button = None
        self.take_photo_button = None

        self.showing_camera = True
        self.showing_gif = False

        self.manual_photo_dir = "Manual_Photos"
        self.manual_raw_dir = os.path.join(self.manual_photo_dir, "raw")
        self.manual_pgm_dir = os.path.join(self.manual_photo_dir, "pgm")
        os.makedirs(self.manual_raw_dir, exist_ok=True)
        os.makedirs(self.manual_pgm_dir, exist_ok=True)

        self.raw_dir = None

    def _require_wavelength_nm(self) -> float:
        if self.wavelength is None:
            raise RuntimeError(
                "Wavelength not set (self.wavelength is None). "
                "Turn on laser (so get_laser_info returns wavelength) or set wavelength in Hand mode."
            )
        return float(self.wavelength)

    def _lam_mm(self) -> float:
        return self._require_wavelength_nm() * 1e-6

    def _idx_from_steps(self, steps: int, steps_per_mm: int) -> int:
        return int(steps // steps_per_mm)

    def _z_mm_from_idx(self, idx: int) -> float:
        return float(idx)

    def _add_measurement_record(self, measurements, idx: int, res):
        dx_mm = float(res.Dx_mm)
        dy_mm = float(res.Dy_mm)
        measurements.append(
            {
                "idx": int(idx),
                "z_mm": self._z_mm_from_idx(int(idx)),
                "dx_mm": dx_mm,
                "dy_mm": dy_mm,
            }
        )

    def _compute_m2_from_records(self, measurements, title: str):
        if not measurements:
            raise RuntimeError("No measurement points collected.")

        z_mm = np.array([m["z_mm"] for m in measurements], dtype=float)
        dx_mm = np.array([m["dx_mm"] for m in measurements], dtype=float)
        dy_mm = np.array([m["dy_mm"] for m in measurements], dtype=float)

        if not (len(z_mm) == len(dx_mm) == len(dy_mm)):
            # This should never happen now, but keep a hard guard.
            n = min(len(z_mm), len(dx_mm), len(dy_mm))
            z_mm, dx_mm, dy_mm = z_mm[:n], dx_mm[:n], dy_mm[:n]

        if len(z_mm) < 8:
            raise RuntimeError(f"Not enough points for M² (need >= 8, have {len(z_mm)}).")

        lam_mm = self._lam_mm()

        return compute_m2_hyperbola(
            z_mm, dx_mm, dy_mm, lam_mm,
            metric="1e2_diameter",
            z_window=(70.0, 135.0),
            min_points=8,
            return_fig=True,
            units="mm",
            title=title
        )

    def save_current_frame(self):
        try:
            if self.latest_frame is None:
                print("No frame to save (latest_frame is None).")
                return
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"frame_{timestamp}.png"
            cv2.imwrite(filename, self.latest_frame)
            print(f"Saved frame: {filename}")
        except Exception as ex:
            print(f"Error saving frame: {ex}")
            print(f"Error details: {traceback.format_exc()}")

    def connect_camera(self) -> bool:
        if self.cam is not None:
            return True
        try:
            self.camera_conn = FlirCameraConnection(self.config_path)
            self.camera_conn.connect()
            self.cam = self.camera_conn.cam

            try:
                set_default_configuration(self, self.cam)
            except Exception:
                traceback.print_exc()

            try:
                for _ in range(10):
                    _ = SimpleCameraCapture.capture_image_at_position(
                        self, self.cam, position=None, previous_sat=self.previous_saturation_level
                    )
            except Exception:
                pass

            return True
        except Exception:
            traceback.print_exc()
            self.camera_conn = None
            self.cam = None
            return False

    def disconnect_camera(self):
        try:
            if self.camera_conn is not None:
                self.camera_conn.disconnect()
        except Exception:
            traceback.print_exc()
        finally:
            self.camera_conn = None
            self.cam = None

    # --------------------- UI helpers ---------------------
    def _axis_go_to(self, axis_no: int, pos_steps: int):
        try:
            return self.axis_service.go_to(axis_no=axis_no, position=pos_steps)
        except TypeError:
            pass
        try:
            return self.axis_service.go_to(axis_no=axis_no, pos=pos_steps)
        except TypeError:
            pass
        try:
            return self.axis_service.go_to(axis_no=axis_no, steps=pos_steps)
        except TypeError:
            pass
        return self.axis_service.go_to(axis_no, pos_steps)

    def _ui_status(self, text: str):
        if self.axis_status_label:
            ui_call(self.axis_status_label, lambda: self.axis_status_label.config(text=text))

    def _ui_buttons_running(self, running: bool):
        def apply():
            if self.start_button:
                self.start_button.config(state=tk.DISABLED if running else tk.NORMAL)
            if self.stop_button:
                self.stop_button.config(state=tk.NORMAL)
            if self.focus_button:
                self.focus_button.config(state=tk.DISABLED if running else tk.NORMAL)
            if self.test_button:
                self.test_button.config(state=tk.DISABLED if running else tk.NORMAL)

        if self.camera_label:
            ui_call(self.camera_label, apply)
        else:
            apply()

    def show_laser_status_non_blocking(self, text: str):
        parent = getattr(self, "root", None) or getattr(self, "master", None)
        if parent is None:
            return
        win = tk.Toplevel(parent)
        win.title("Laser status")
        win.transient(parent)

        frame = tk.Frame(win, padx=10, pady=10)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=text, justify="left").pack(anchor="w")

        win.after(3000, win.destroy)

    def connect_to_axis(self):
        if self.axis_button:
            self.axis_button.config(state=tk.DISABLED)
        self._ui_status("Connecting...")

        def worker():
            try:
                ctrl = self.axis_service.connect(timeout_sec=12.0)
                self.axis_controller = ctrl
                self.axis_connected = True
                self.axis_service.attach_camera(self.cam)
                self._ui_status("Connected")
            except Exception as e:
                self.axis_connected = False
                self.axis_controller = None
                self._ui_status(f"Axis error: {e}")
                traceback.print_exc()
            finally:
                if self.axis_button:
                    ui_call(self.axis_button, lambda: self.axis_button.config(state=tk.NORMAL))

        Thread(target=worker, daemon=True).start()

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
            _info, serial, model, wavelength = self.laser_service.get_laser_info()

            if serial:
                self.serial = serial
            if model:
                self.model = model
            if wavelength:
                self.wavelength = wavelength

            if self.laser_button:
                self.laser_button.config(text="Turn OFF Laser", bg="red")

            status_text = (
                "Laser successfully activated\n"
                f"Wavelength: {self.wavelength} nm\n"
                f"Serial number: {self.serial}\n"
                f"Model: {self.model}"
            )
            self.show_laser_status_non_blocking(status_text)

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Laser controller error", f"Unable to control the laser: {e}")

    def laser_auto_off(self):
        if self.laser_service is not None:
            try:
                self.laser_service.turn_off()
            except Exception:
                pass

    def run(self):
        if self.running:
            return True

        if not self.connect_camera():
            return False

        self.running = True
        self.display_running = True

        self.worker_thread = Thread(target=camera_worker_task, args=(self, self.cam), daemon=True)
        self.worker_thread.start()

        if self.camera_label:
            self.camera_label.after(100, self.display_frame_in_tkinter)

        return True

    def stop(self):
        self.running = False
        self.display_running = False

        try:
            if self.worker_thread and self.worker_thread.is_alive():
                self.worker_thread.join(timeout=5.0)
        except Exception:
            pass
        self.worker_thread = None

        self.laser_auto_off()
        self.disconnect_camera()

        self.axis_connected = False
        self.axis_controller = None

        print("Camera stopped cleanly.")

    def display_frame_in_tkinter(self):
        if not self.running:
            return

        if (hasattr(self, "showing_camera") and not self.showing_camera) or \
           (hasattr(self, "showing_gif") and self.showing_gif):
            if self.camera_label:
                self.camera_label.after(33, self.display_frame_in_tkinter)
            return

        try:
            if self.latest_frame is not None and self.camera_label is not None:
                lw = self.camera_label.winfo_width()
                lh = self.camera_label.winfo_height()

                photo = prepare_for_tk(
                    self.latest_frame, lw, lh,
                    self.last_known_exposure_time,
                    self.previous_saturation_level,
                    self.previous_background_level
                )
                if photo is not None:
                    self.camera_label.config(image=photo)
                    self.camera_label.image = photo

            if self.camera_label:
                self.camera_label.after(33, self.display_frame_in_tkinter)

        except Exception:
            traceback.print_exc()
            if self.camera_label:
                self.camera_label.after(100, self.display_frame_in_tkinter)

    # --------------------- HAND MODE ---------------------
    def hand_mode(self):
        lam, folder = hand_mode_dialog(self, initial_wavelength=self.wavelength)
        if lam is None or folder is None:
            return

        self.wavelength = lam

        data_dic = read_data_folder(folder)
        if not data_dic:
            messagebox.showerror("Klaida", "Folderyje nerasta tinkamų failų (su skaičiumi pavadinime).")
            return

        measurements = []
        for z_val, arr in data_dic.items():
            res = beam_size_k4_fixed_axes(arr, pixel_size_um=3.75, k=4.0)
            try:
                idx = int(float(z_val))  # your folder keys are typically numbers
            except Exception:
                # fallback: try normalize string
                idx = int(float(_norm_name(z_val)))
            self._add_measurement_record(measurements, idx, res)

        try:
            (results, fig) = self._compute_m2_from_records(
                measurements,
                title=f"Manual ({self.wavelength} nm)"
            )
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error", f"M² computation failed: {e}")
            return

        if fig is None:
            messagebox.showwarning("Įspėjimas", "Nepavyko sugeneruoti M² grafiko.")
            return

        self.measurement_figure = fig
        try:
            from utils.storage_utils import StorageUtilities
            StorageUtilities.store_figure(self, fig)
        except Exception:
            pass

        if self.figure_button:
            self.figure_button.config(state=tk.NORMAL)
        if self.save_data_button:
            self.save_data_button.config(state=tk.NORMAL)

        self.show_figure()

    # --------------------- Focus finding ---------------------
    def find_focus_process(self):
        if not self.axis_connected or self.axis_controller is None:
            messagebox.showerror("Error", "First connect to the axis!")
            return
        if self.cam is None:
            messagebox.showerror("Error", "Camera not initialized!")
            return

        self.stop_event.clear()
        self.stop_requested = False
        self.process_running = True

        self._ui_buttons_running(True)
        self._ui_status("Looking for a focal point")

        def thread_fn():
            try:
                max_length = self.get_from_settings_json("length_of_runners")
                step_size = 1587  # steps per mm


                # Kad nuotraukos būtų daromos greičiau, per fokusavimo paiešką acquisition paleidžiam vieną kartą.
                _acq_started = False
                try:
                    if self.cam is not None and hasattr(self.cam, "IsStreaming") and not self.cam.IsStreaming():
                        self.cam.BeginAcquisition()
                        _acq_started = True
                except Exception:
                    _acq_started = False

                try:
                    focus_steps = find_focus(
                        axis_service=self.axis_service,
                        capture_fn=lambda pos: self.measure.capture_image(pos),
                        beam_fn=lambda img: beam_size_k4_fixed_axes(img, pixel_size_um=3.75, k=4.0),
                        axis_no=0,
                        max_position=max_length,
                        step_size=step_size,
                        stop_event=self.stop_event
                    )
                finally:
                    try:
                        if _acq_started and self.cam is not None and hasattr(self.cam, "IsStreaming") and self.cam.IsStreaming():
                            self.cam.EndAcquisition()
                    except Exception:
                        pass

                if self.stop_event.is_set():
                    self._ui_status("Proceedings suspended")
                    return

                if focus_steps is not None:
                    best_focus_mm = float(focus_steps) / step_size
                    change_val("focus_position", best_focus_mm / 2.0)
                    self._ui_status(f"Focus found: {best_focus_mm:.3f} mm")
                else:
                    self._ui_status("Focus not found")

            except Exception as e:
                traceback.print_exc()
                self._ui_status(f"Error finding focus: {e}")
            finally:
                self.process_running = False
                self._ui_buttons_running(False)

        Thread(target=thread_fn, daemon=True).start()

    # --------------------- figure/gif display ---------------------
    def show_gif(self):
        if not self.gif_path or not os.path.exists(self.gif_path):
            return

        try:
            self.showing_camera = False
            self.showing_gif = True

            gif = Image.open(self.gif_path)
            from gif.gif import animate_gif
            animate_gif(self.camera_label, gif, lambda: self.showing_gif)

            if self.figure_button:
                self.figure_button.config(state=tk.NORMAL)
            if self.camera_button:
                self.camera_button.config(state=tk.NORMAL)
            if self.gif_button:
                self.gif_button.config(state=tk.DISABLED)
            if self.save_data_button:
                self.save_data_button.config(state=tk.NORMAL)

        except Exception:
            traceback.print_exc()
            self.showing_camera = True
            self.showing_gif = False

    def show_figure(self):
        if self.measurement_figure is None or self.camera_label is None:
            return

        try:
            self.showing_camera = False
            self.showing_gif = False

            canvas = backend_agg.FigureCanvasAgg(self.measurement_figure)
            canvas.draw()

            w, h = self.measurement_figure.get_size_inches() * self.measurement_figure.get_dpi()
            w, h = int(w), int(h)

            img = Image.frombuffer("RGB", (w, h), canvas.buffer_rgba(), "raw", "RGBA", 0, 1)

            lw = self.camera_label.winfo_width()
            lh = self.camera_label.winfo_height()

            if lw > 1 and lh > 1:
                img_ratio = img.width / img.height
                label_ratio = lw / lh
                if img_ratio > label_ratio:
                    new_w = lw
                    new_h = int(lw / img_ratio)
                else:
                    new_h = lh
                    new_w = int(lh * img_ratio)
                img = img.resize((new_w, new_h), Image.LANCZOS)

            photo = ImageTk.PhotoImage(image=img)
            self.camera_label.config(image=photo)
            self.camera_label.image = photo

            if self.figure_button:
                self.figure_button.config(state=tk.DISABLED)
            if self.camera_button:
                self.camera_button.config(state=tk.NORMAL)
            if self.gif_button and self.gif_path:
                self.gif_button.config(state=tk.NORMAL)

        except Exception:
            traceback.print_exc()
            self.showing_camera = True
            self.showing_gif = False

    def show_camera(self):
        self.showing_camera = True
        self.showing_gif = False

        if self.figure_button and self.measurement_figure is not None:
            self.figure_button.config(state=tk.NORMAL)
        if self.camera_button:
            self.camera_button.config(state=tk.DISABLED)
        if self.gif_button and self.gif_path:
            self.gif_button.config(state=tk.NORMAL)

    # --------------------- capture/save/measure ---------------------
    def capture_save_measure(self, position_steps: int, idx: int, raw_dir: str, pgm_dir: str, current_position=None):
        img = SimpleCameraCapture.capture_image_at_position(
            self, self.cam, current_position, self.previous_saturation_level
        )
        if img is None:
            return None, None

        filename = str(int(idx))
        self.images_dict[filename] = img.copy()

        _save_data(self, raw_dir, pgm_dir, img, filename, position_steps, position_steps)

        res = beam_size_k4_fixed_axes(img, pixel_size_um=3.75, k=4.0)
        return img, res

    # --------------------- Main process ---------------------
    def start_process(self):
        if self.process_running:
            return

        if not self.axis_connected or self.axis_controller is None:
            messagebox.showerror("Error", "Axis controller is not connected.")
            return
        if self.cam is None:
            messagebox.showerror("Error", "Camera is not connected.")
            return

        self.process_running = True
        self.stop_requested = False
        self.stop_event.clear()
        self.images_dict.clear()

        self._ui_buttons_running(True)
        self._ui_status("Ongoing...")

        Thread(target=self._start_process_worker, daemon=True).start()

    def _start_process_worker(self):
        folder_name = None
        time1 = None
        try:
            measurment_t1 = time.time()
            self.toggle_laser()
            _ = self._lam_mm()  # validates wavelength; value is used later

            folder_name = f"M2_Data_{self.serial}_{self.model}_{time.strftime('%Y-%m-%d_%H-%M-%S')}"
            raw_dir = os.path.join(folder_name, "raw")
            pgm_dir = os.path.join(folder_name, "pgm")
            analysis_dir = os.path.join(folder_name, "analysis")
            os.makedirs(raw_dir, exist_ok=True)
            os.makedirs(pgm_dir, exist_ok=True)
            os.makedirs(analysis_dir, exist_ok=True)

            max_length = self.get_from_settings_json("length_of_runners")  # steps
            step_size = 1587  # steps per mm (as in your original code)

            measurements = []  # authoritative list (prevents broadcast mismatch)
            current = 0
            prev_area = None
            inc_count = 0
            track_positions = None

            while current <= max_length and not self.stop_event.is_set():
                if time1 is None:
                    time1 = time.time()

                self._axis_go_to(axis_no=0, pos_steps=current)
                idx = self._idx_from_steps(current, step_size)

                img, res = self.capture_save_measure(current, idx, raw_dir, pgm_dir)
                if res is None:
                    current += step_size
                    continue

                self._add_measurement_record(measurements, idx, res)

                area = float(res.Dx_mm) * float(res.Dy_mm)
                if prev_area is not None and area > prev_area:
                    inc_count += 1
                else:
                    inc_count = 0
                prev_area = area

                if inc_count >= 5:
                    focus_mm = float(current) / float(step_size)
                    max_mm = float(max_length) / float(step_size)

                    raw_track = generate_track_by_focus(focus_mm, max_mm, 1.0)
                    track_positions = track_to_step_positions(
                        track=raw_track,
                        steps_per_mm=step_size,
                        max_steps=max_length
                    )

                    if DEBUG_TRACK:
                        print("=== TRACK DEBUG ===")
                        print("focus_mm:", focus_mm, "max_mm:", max_mm)
                        print("raw_track sample:", raw_track[:10] if raw_track else raw_track)
                        print("track_positions sample:", track_positions[:10] if track_positions else track_positions)
                        print("===================")

                    prune_everything(
                        track_positions=track_positions,
                        step_size=step_size,
                        raw_dir=raw_dir,
                        pgm_dir=pgm_dir,
                        images_dict=self.images_dict,
                        measurements=measurements
                    )

                    start_i = bisect.bisect_right(track_positions, current)
                    measured_idx = {m["idx"] for m in measurements}

                    for x in track_positions[start_i:]:
                        if self.stop_event.is_set():
                            break

                        idx2 = self._idx_from_steps(x, step_size)
                        if idx2 in measured_idx:
                            continue

                        self._axis_go_to(axis_no=0, pos_steps=x)
                        _img2, res2 = self.capture_save_measure(x, idx2, raw_dir, pgm_dir)
                        if res2 is None:
                            continue

                        self._add_measurement_record(measurements, idx2, res2)
                        measured_idx.add(idx2)

                    self.stop_event.set()
                    break

                current += step_size


            if len(measurements) < 8:
                ui_call(self.camera_label, lambda: self._ui_status("Stopped / not enough points for M²"))
                try:
                    self.axis_controller._go_home(axis_no=0)
                except Exception:
                    pass
                return

            (results, fig) = self._compute_m2_from_records(
                measurements,
                title=f"Auto ({self.wavelength} nm)"
            )

            if fig is None:
                ui_call(self.camera_label, lambda: self._ui_status("M² figure not produced"))
                return
            measurment_t2 = time.time()



            print(f"Measurement time: {measurment_t2 - measurment_t1:.2f} seconds")
            self.measurement_figure = fig
            if self.figure_button:
                ui_call(self.figure_button, lambda: self.figure_button.config(state=tk.NORMAL))
            if self.save_data_button:
                ui_call(self.save_data_button, lambda: self.save_data_button.config(state=tk.NORMAL))

            ui_call(self.camera_label, lambda: self._ui_status("The process is complete"))

            # Optional: go home
            try:
                self.axis_controller._go_home(axis_no=0)
            except Exception:
                pass

            if time1 is not None:
                try:
                    print(f"Kiek laiko truko: {time.time() - time1}")
                except Exception:
                    pass

        except Exception as e:
            traceback.print_exc()
            err = str(e)
            ui_call(self.camera_label, lambda: self._ui_status(f"Error: {err}"))
            ui_call(self.camera_label, lambda: messagebox.showerror("Error", f"The process has failed: {err}"))

        finally:
            self.process_running = False
            ui_call(self.camera_label, lambda: self._ui_buttons_running(False))

    def stop_process(self):
        if not self.axis_connected or self.axis_controller is None:
            messagebox.showerror("Error", "Not connected to the axis!")
            return

        self.stop_requested = True
        self.stop_event.set()
        self._ui_status("Stopping...")

        def thread_fn():
            try:
                if self.axis_service.is_alive():
                    try:
                        self.axis_service.stop_all()
                    except Exception:
                        pass
                if self.axis_service.is_alive():
                    try:
                        self.axis_service.home(0)
                    except Exception:
                        pass

                self.process_running = False
                self._ui_status("The process is suspended")

            except Exception as e:
                traceback.print_exc()
                self._ui_status(f"Error: failed to stop ({e})")
                ui_call(self.camera_label, lambda: messagebox.showerror("Error", f"Failed to stop: {e}"))
            finally:
                self._ui_buttons_running(False)

        Thread(target=thread_fn, daemon=True).start()

    def test_axis(self):
        def thread_fn():
            try:
                if not self.connect_camera():
                    raise RuntimeError("Camera not connected")

                ctrl = self.axis_service.connect(timeout_sec=12.0)
                self.axis_controller = ctrl
                self.axis_connected = True
                self.axis_service.attach_camera(self.cam)
                self._ui_status("Testing...")

                steps_per_mm, axis_position = self.axis_service.initialize_axis()

                result_message = "Axis initialization completed\n"
                if steps_per_mm is not None:
                    result_message += f"Steps per mm: {float(steps_per_mm)}\n"
                if axis_position is not None:
                    result_message += f"Axis position: {axis_position} steps\n"
                    max_range_mm = float(axis_position) / float(steps_per_mm) if steps_per_mm else 0.0
                    result_message += f"Maximum range: {max_range_mm:.2f} mm ({max_range_mm/10:.2f} cm)"

                change_val("length_of_runners", axis_position)
                change_val("step_per_mm", float(steps_per_mm) if steps_per_mm else 0.0)

                self._ui_status("The test is finished")
                ui_call(self.camera_label, lambda: messagebox.showinfo("Axis test", result_message))

            except Exception as e:
                traceback.print_exc()
                self._ui_status(f"Error: test failed ({e})")
                ui_call(self.camera_label, lambda: messagebox.showerror("Error", f"Failed to initialise axis: {e}"))
            finally:
                self.process_running = False
                self._ui_buttons_running(False)

        self._ui_buttons_running(True)
        Thread(target=thread_fn, daemon=True).start()

    def take_photo(self, filename: str):
        if self.cam is None:
            messagebox.showerror("Photo Error", "Kamera neinicijuota.")
            return

        try:
            img = SimpleCameraCapture.capture_image_at_position(
                self, self.cam, position=None, previous_sat=self.previous_saturation_level
            )

            if img is None:
                messagebox.showwarning(
                    "Photo",
                    f"Nepavyko gauti tinkamo kadro.\n"
                    f"Saturation turi būti [{self.params.saturation_lower_bound}, {self.params.saturation_upper_bound}]."
                )
                return

            base_name = filename
            i = 1
            while base_name in self.images_dict:
                base_name = f"{filename}_{i}"
                i += 1

            self.images_dict[base_name] = img.copy()
            _save_data(self, self.manual_raw_dir, self.manual_pgm_dir, img, base_name, 0, 0)

            messagebox.showinfo("Photo saved", f"Nuotrauka išsaugota:\nManual_Photos/{base_name}")

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Photo Error", f"Klaida darant nuotrauką:\n{e}")

    def save_data(self):
        try:
            has_gif = self.gif_path is not None
            has_fig = self.measurement_figure is not None

            if not has_gif and not has_fig:
                messagebox.showwarning("Warning", "No data that can be saved.")
                return

            if has_gif:
                original_basename = os.path.basename(self.gif_path)
                original_name = os.path.splitext(original_basename)[0]
            else:
                original_name = f"measurement_{time.strftime('%Y%m%d_%H%M%S')}"

            if has_gif and not os.path.exists(self.gif_path):
                alt = os.path.join(os.getcwd(), os.path.basename(self.gif_path))
                if os.path.exists(alt):
                    self.gif_path = alt
                else:
                    has_gif = False

            save_directory = filedialog.askdirectory(title="Select the directory where you want to save the data")
            if not save_directory:
                return

            saved = self.storage.copy_results_to_folder(
                save_directory=save_directory,
                original_name=original_name,
                gif_path=self.gif_path if has_gif else None,
                fig=self.measurement_figure if has_fig else None
            )

            if saved:
                messagebox.showinfo(
                    "Succesfully saved",
                    "Data successfully saved in the catalogue:\n"
                    f"{save_directory}\n\nSaved files:\n" + "\n".join(saved)
                )
            else:
                messagebox.showwarning("Attention", "Could not save any files.")

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to save data: {e}")

    def get_from_settings_json(self, key: str):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, "config", "setting.json")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data["CameraDefaultSettings"][key]