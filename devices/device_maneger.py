import threading
import time
import traceback
import re

import tkinter as tk
from tkinter import ttk, messagebox

from config.environment_config import EnvironmentConfig
from devices.global_devices import GlobalDevices
from devices.devices_runner import DevicesRunner

# Šitie importai palikti, bet jie bus naudojami tik jeigu init_camera=True
from devices.camera.camera_connection import FlirCameraConnection
from devices.camera.Image.image_saturation import ImageSaturationProcessor


class DeviceManager:
    def __init__(self, config_path="camera_config.json"):
        self.axis_controller = None

        self.camera = None
        self.saturation_processor = None
        self.config_path = config_path

        self.device_runner = None
        self.device_runner_thread = None

    def _load_environment(self):
        config = EnvironmentConfig()
        config.validate_environment()

    def _start_device_runner(self):
        if self.device_runner_thread is not None and self.device_runner_thread.is_alive():
            return

        self.device_runner = DevicesRunner()
        self.device_runner_thread = threading.Thread(
            target=self.device_runner.run,
            daemon=True
        )
        self.device_runner_thread.start()

    def _init_camera_optional(self):
        if self.camera is not None:
            return True, "Camera already initialized."

        try:
            self.camera = FlirCameraConnection(self.config_path)
            cam, system, cam_list = self.camera.connect()

            if cam is None:
                self.camera = None
                return False, "Failed to init camera (cam is None)."

            self.saturation_processor = ImageSaturationProcessor(pkl_file="saturation_data.pkl")
            return True, "Camera initialized."
        except Exception as e:
            traceback.print_exc()
            self.camera = None
            self.saturation_processor = None
            return False, f"Camera init error: {e}"

    def _wait_axis_controller(self, timeout_sec: float = 10.0):
        start = time.time()
        last_print = 0.0

        while time.time() - start < timeout_sec:
            self.axis_controller = GlobalDevices().get_axis_controller()

            now = time.time()
            if now - last_print >= 1.0:
                print("Waiting for axis_controller... current:", self.axis_controller)
                last_print = now

            if self.axis_controller is not None:
                return True, "Axis controller acquired."

            time.sleep(0.2)

        self.axis_controller = None
        return False, "Axis controller not created (timeout)."

    def _attach_camera_to_axis_if_any(self):
        if self.axis_controller is None:
            return

        if self.camera is None:
            return

        try:
            if hasattr(self.axis_controller, "cam") and self.camera is not None:
                self.axis_controller.cam = self.camera.cam

            self.axis_controller.saturation_processor = self.saturation_processor
            self.axis_controller.saturation_min = 190
            self.axis_controller.saturation_max = 210
        except Exception:
            traceback.print_exc()


    def init_devices(self, init_camera: bool = False, axis_timeout_sec: float = 12.0):
        try:
            self._load_environment()
            self._start_device_runner()

            if init_camera:
                ok_cam, msg_cam = self._init_camera_optional()
                if not ok_cam:
                    return False, msg_cam

            ok_axis, msg_axis = self._wait_axis_controller(timeout_sec=axis_timeout_sec)
            if not ok_axis:
                return False, msg_axis

            if init_camera:
                self._attach_camera_to_axis_if_any()

            return True, "Devices initialized successfully."

        except Exception as e:
            traceback.print_exc()
            self.axis_controller = None
            return False, f"DeviceManager.init_devices exception: {e}"

class MainWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Measurement GUI")

        self.device_manager = DeviceManager()
        self.axis_controller = None
        self.axis_connected = False

        self.laser_on = False
        self.wavelength = None
        self.serial = None
        self.model = None

        self._build_ui()

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill="both", expand=True)

        self.status_label = ttk.Label(main_frame, text="Not connected")
        self.status_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        connect_btn = ttk.Button(main_frame, text="Connect axis", command=self.on_connect_devices)
        connect_btn.grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)

        self.laser_button = tk.Button(main_frame, text="Turn ON Laser", bg="green", command=self.toggle_laser)
        self.laser_button.grid(row=1, column=1, sticky="w", pady=5)

        main_frame.columnconfigure(0, weight=0)
        main_frame.columnconfigure(1, weight=0)

    def show_toast(self, title: str, text: str, duration_ms: int = 3000):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)

        label = ttk.Label(frame, text=text, justify="left")
        label.pack(anchor="w")

        win.after(duration_ms, win.destroy)

    def on_connect_devices(self):
        self.status_label.config(text="Connecting axis...")
        threading.Thread(target=self._connect_devices_worker, daemon=True).start()

    def _connect_devices_worker(self):
        success, msg = self.device_manager.init_devices(init_camera=False)
        if success:
            self.axis_controller = self.device_manager.axis_controller
            self.axis_connected = self.axis_controller is not None
        else:
            self.axis_connected = False
            self.axis_controller = None

        self.root.after(0, lambda: self._connect_devices_done(success, msg))

    def _connect_devices_done(self, success: bool, msg: str):
        if success:
            self.status_label.config(text=msg)
            self.show_toast("Devices", msg, duration_ms=1500)
        else:
            self.status_label.config(text="Error: " + msg)
            messagebox.showerror("Devices error", msg)

    def parse_wavelength(self, model: str):
        m = re.search(r"(\d+)$", model)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return None
        return None

    def toggle_laser(self):
        try:
            if self.axis_controller is None or not self.axis_connected:
                messagebox.showerror("Laser controller error", "First connect axis.")
                return

            laser = self.axis_controller

            if self.laser_on:
                try:
                    laser.set_laser_off()
                except Exception:
                    pass
                self.laser_on = False
                self.laser_button.config(text="Turn ON Laser", bg="green")
                self.show_toast("Laser status", "Laser OFF", duration_ms=1500)
                return

            laser.set_laser_power()
            laser.set_laser_on()
            self.laser_on = True
            self.laser_button.config(text="Turn OFF Laser", bg="red")

            info = None
            try:
                info = laser.get_laser_info()
            except Exception:
                traceback.print_exc()

            if info:
                s_n = re.search(r"S/N:\s*([^\s]+)", info)
                if s_n:
                    self.serial = s_n.group(1)

                model_raw = re.search(r"model:\s*([^\s]+)", info)
                if model_raw:
                    self.model = model_raw.group(1)
                    self.wavelength = self.parse_wavelength(self.model)

            status_text = (
                "Laser successfully activated\n"
                f"Wavelength: {self.wavelength} nm\n"
                f"Serial number: {self.serial}\n"
                f"Model: {self.model}"
            )
            self.show_toast("Laser status", status_text, duration_ms=3000)

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Laser controller error", f"Unable to control the laser: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()
