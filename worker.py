import os
import time
import json
import shutil
import cv2
import threading
import traceback
import numpy as np
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

from devices.camera.camera_service import CameraService
from devices.camera.camera_display import prepare_for_tk

from devices.axis.axis_service import AxisService
from devices.laser.laser_service import LaserService
from measurement.focus import find_focus
from measurement.measurement_service import MeasurementService
from storage.storage_service import StorageService

from measurement.calculations import beam_size_k4_fixed_axes
from measurement.quadrometer import compute_m2_hyperbola


class CameraWorker:
    def __init__(self, config_path="camera_config.json"):
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

        # Camera settings dictionary
        self.camera_settings = {
            'width': 1288,
            'height': 964,
            'gain': 0,
            'brightness': 2,
            'frame_rate': 30
        }

        # Frame counter for camera acquisition
        self.frame_count = 0
        self.start_time = None

        self.camera_service = CameraService(serial_number=self.serial_number)
        self.cam = None

        base_dir = os.path.dirname(os.path.abspath(__file__))
        setings_path = os.path.join(base_dir, "config", "setting.json")
        self.device_manager = DeviceManager(config_path=setings_path)

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

        print("CameraWorker ready.")
        print("Defaults:", self.camera_defaults)

    def _ui_status(self, text: str):
        if self.axis_status_label:
            ui_call(self.axis_status_label, lambda: self.axis_status_label.config(text=text))

    def _ui_buttons_running(self, running: bool):
        def apply():
            if self.start_button:
                self.start_button.config(state=tk.DISABLED if running else tk.NORMAL)
            if self.stop_button:
                self.stop_button.config(state=tk.NORMAL if running else tk.NORMAL)
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

    def save_current_frame(self):
        try:
            if self.latest_frame is not None:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"frame_{timestamp}.png"
                cv2.imwrite(filename, self.latest_frame)
            else:
                print("No frame to save")
        except Exception as ex:
            print(f"Error saving frame: {ex}")
            print(f"Error details: {traceback.format_exc()}")

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
        cam = self.camera_service.start()
        if cam is None:
            return False

        self.cam = cam
        try:
            set_default_configuration(self, self.cam)
        except Exception:
            traceback.print_exc()

        self.running = True

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

        try:
            self.camera_service.stop()
        except Exception:
            traceback.print_exc()

        self.cam = None
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

    def show_gif(self):
        if not self.gif_path or not os.path.exists(self.gif_path):
            return

        try:
            self.showing_camera = False
            self.showing_gif = True

            gif = Image.open(self.gif_path)

            # tavo animate_gif funkcija
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

    # --------------------- HAND MODE ---------------------
    def hand_mode(self):
        lam, folder = hand_mode_dialog(self, initial_wavelength=self.wavelength)
        if lam is None or folder is None:
            return

        self.wavelength = lam

        # nuskaityti data iš folderio
        data_dic = read_data_folder(folder)
        if not data_dic:
            messagebox.showerror("Klaida", "Folderyje nerasta tinkamų failų (su skaičiumi pavadinime).")
            return

        dx_list, dy_list, z_list = [], [], []
        for z_val, arr in data_dic.items():
            res = beam_size_k4_fixed_axes(arr, pixel_size_um=3.75, k=4.0)
            dx_list.append(res.Dx_mm)
            dy_list.append(res.Dy_mm)
            z_list.append(z_val)

        # tavo konversijos
        dx = np.array(dx_list, dtype=float) * 1e-3
        dy = np.array(dy_list, dtype=float) * 1e-3
        z  = np.array(z_list,  dtype=float) * 1e-3
        lam_m = self.wavelength * 1e-9

        (results, fig) = compute_m2_hyperbola(
            z, dx, dy, lam_m,
            metric="1e2_diameter",
            z_window=(70.0, 135.0),
            use_huber=True,
            reject_outliers=True,
            reject_k=3.0,
            max_passes=3,
            min_points=8,
            return_fig=True,
            units="mm",
            title=f"Manual ({self.wavelength} nm)"
        )

        print(results)

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

    # --------------------- FOCUS PROCESS ---------------------
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
                # max_length iš json (palieku tavo metodą)
                max_length = self.get_from_settings_json("length_of_runners")
                step_size = 1587

                focus_steps = find_focus(
                    axis_service=self.axis_service,
                    capture_fn=lambda pos: self.measure.capture_image(pos),
                    beam_fn=lambda img: beam_size_k4_fixed_axes(img, pixel_size_um=3.75, k=4.0),
                    axis_no=0,
                    max_position=max_length,
                    step_size=step_size,
                    stop_event=self.stop_event
                )

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

    # --------------------- START / STOP MAIN MEASUREMENT ---------------------
    def start_process(self):
        if not self.axis_connected or self.axis_controller is None:
            messagebox.showerror("Error", "First connect to the axis!")
            return
        if self.cam is None:
            messagebox.showerror("Error", "Camera not initialized!")
            return

        self.process_running = True
        self.stop_requested = False
        self.stop_event.clear()
        self.images_dict.clear()
        self.gif_path = None
        self.measurement_figure = None

        self._ui_buttons_running(True)
        self._ui_status("Ongoing...")

        def thread_fn():
            folder_name = None
            meta_df = None

            try:
                # lazeris ON
                self.toggle_laser()

                # 1) fokusas (jei jau turi focus_position – gali praleisti; bet palieku kaip pilną)
                max_length = self.get_from_settings_json("length_of_runners")
                step_size = 1587

                focus_steps = find_focus(
                    axis_service=self.axis_service,
                    capture_fn=lambda pos: self.measure.capture_image(pos),
                    beam_fn=lambda img: beam_size_k4_fixed_axes(img, pixel_size_um=3.75, k=4.0),
                    axis_no=0,
                    max_position=max_length,
                    step_size=step_size,
                    stop_event=self.stop_event
                )

                if self.stop_requested or self.stop_event.is_set():
                    self._ui_status("Proceedings suspended")
                    return

                if focus_steps is None:
                    self._ui_status("Focus not found")
                    return

                best_focus_mm = float(focus_steps) / step_size
                change_val("focus_position", best_focus_mm / 2.0)

                # 2) track scan
                focus_point = self.get_from_settings_json("focus_position")  # mm (pas tave)
                focus_steps_for_track = focus_point * 2  # palieku tavo logiką

                folder_name = f"M2_Data_{self.serial}_{self.model}_{time.strftime('%Y-%m-%d_%H-%M-%S')}"
                (folder_name, raw_dir, pgm_dir, z_list, dx_list, dy_list, meta_df) = self.measure.run_track_scan(
                    axis_service=self.axis_service,
                    focus_pos_steps=focus_steps_for_track,
                    travel_mm=220,
                    step_size=step_size,
                    folder_name=folder_name,
                    stop_flag=lambda: self.stop_requested or self.stop_event.is_set()
                )

                if self.stop_requested or self.stop_event.is_set():
                    self._ui_status("Proceedings suspended")
                    return

                if not self.images_dict:
                    self._ui_status("Measurement omitted: no data")
                    try:
                        self.axis_service.home(0)
                    except Exception:
                        pass
                    return

                # 3) go home (thread)
                go_home_thread = Thread(target=lambda: self.axis_service.home(0), daemon=True)
                go_home_thread.start()

                # 4) lygiagrečiai: GIF
                gif_result = {"path": None}

                def gif_job():
                    gif_result["path"] = self.measure.create_gif_async(folder_name)

                gif_thread = Thread(target=gif_job, daemon=True)
                gif_thread.start()

                # 5) M²
                if self.wavelength is None:
                    raise RuntimeError("Wavelength is None (laser info not parsed).")

                results, fig = self.measure.compute_m2(
                    z_list, dx_list, dy_list,
                    wavelength_nm=self.wavelength,
                    title=f"{self.model} ({self.serial})"
                )

                print(results)

                self.measurement_figure = fig

                # 6) save fig + txt
                if fig is not None:
                    self.storage.save_figure_png(folder_name, fig, self.serial, self.model)
                    self.storage.save_m2_txt(folder_name, z_list, dx_list, dy_list)

                # 7) wait gif
                gif_thread.join()
                go_home_thread.join()

                self.gif_path = gif_result["path"]
                if self.gif_path:
                    self.storage.store_gif(self.gif_path)

                # 8) UI enable
                if self.figure_button and self.measurement_figure is not None:
                    ui_call(self.figure_button, lambda: self.figure_button.config(state=tk.NORMAL))
                if self.gif_button and self.gif_path is not None:
                    ui_call(self.gif_button, lambda: self.gif_button.config(state=tk.NORMAL))
                if self.save_data_button:
                    ui_call(self.save_data_button, lambda: self.save_data_button.config(state=tk.NORMAL))

                # rodyk figūrą by default
                if self.measurement_figure is not None:
                    ui_call(self.camera_label, self.show_figure)

                self._ui_status("The process is complete")

            except Exception as e:
                traceback.print_exc()
                self._ui_status(f"Error: {e}")
                error_msg = str(e)
                ui_call(self.camera_label, lambda msg=error_msg: messagebox.showerror("Error", f"The process has failed: {msg}"))

            finally:
                self.process_running = False
                self._ui_buttons_running(False)

                # meta csv jei yra
                try:
                    if folder_name and meta_df is not None and not meta_df.empty:
                        meta_df.to_csv(os.path.join(folder_name, f"{folder_name}_meta_data.csv"), index=False)
                except Exception:
                    pass

        Thread(target=thread_fn, daemon=True).start()

    def stop_process(self):
        if not self.axis_connected or self.axis_controller is None:
            messagebox.showerror("Error", "Not connected to the axis!")
            return

        self.stop_requested = True
        self.stop_event.set()
        self._ui_status("...")

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

    # --------------------- TEST AXIS ---------------------
    def test_axis(self):
        def thread_fn():
            try:
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

    # --------------------- PHOTO ---------------------
    def take_photo(self, filename: str):
        if self.cam is None:
            messagebox.showerror("Photo Error", "Kamera neinicijuota.")
            return

        try:
            from Camera.Camera_Capture import SimpleCameraCapture
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

            from helpers.converter import _save_data
            _save_data(self, self.manual_raw_dir, self.manual_pgm_dir, img, base_name, 0, 0)

            messagebox.showinfo("Photo saved", f"Nuotrauka išsaugota:\nManual_Photos/{base_name}")

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Photo Error", f"Klaida darant nuotrauką:\n{e}")

    # --------------------- SAVE DATA (export) ---------------------
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

            # jei gif kelias pasikeitęs
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

    # --------------------- settings.json helpers ---------------------
    def get_from_settings_json(self, key: str):
        """
        Skaito config/setting.json -> CameraDefaultSettings
        (palikta pagal tavo naudojimą; jei ten kita struktūra – pritaikyk)
        """
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, "config", "setting.json")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # jei setting.json turi kitą struktūrą – pakoreguok čia
        # pas tave buvo: data["CameraDefaultSettings"][string]
        return data["CameraDefaultSettings"][key]
