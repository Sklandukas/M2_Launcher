import os
import time
import numpy as np
import traceback
import pandas as pd

from threading import Thread
from storage.converter import _save_data
from measurement.calculations import beam_size_iso11146_vendorlike
from measurement.quadrometer import compute_m2_hyperbola
from measurement.focus import generate_track_by_focus
from devices.camera.camera_service import SimpleCameraCapture
from storage.gif import create_gif_from_arrays
from devices.cooler.CoolerComunication.cooler_data import CoolerData

class MeasurementService:
    def __init__(self, worker):
        self.w = worker

    def capture_image(self, position):
        return SimpleCameraCapture.capture_image_at_position(
            self.w, self.w.cam, position, self.w.previous_saturation_level
        )

    def beam(self, img):
        return beam_size_iso11146_vendorlike(img, 
                                             pixel_size_x_um=3.75, 
                                             pixel_size_y_um=3.75, 
                                             k = 4.0, 
                                             border_px=30,
                                             border_frac_min=0.08,
                                             max_iters=40,
                                             rel_tol=1e-7,
                                             pixel_center=True,
                                             bg_mode="plane",
                                             bg_stat="median",
                                             noise_nsigma=None,
                                             ignore_saturated=False)

    def capture_save_measure(self, position, filename, raw_dir, pgm_dir):
        img = self.capture_image(position)
        if img is None:
            return None, None

        self.w.images_dict[filename] = img.copy()
        _save_data(self.w, raw_dir, pgm_dir, img, filename, position, position)

        res = self.beam(img)
        return img, res

    def run_track_scan(self, axis_service, focus_pos_steps, travel_mm=220, step_size=1587,
                       folder_name=None, stop_flag=None):
        
        w = self.w
        stop_flag = stop_flag or (lambda: False)

        track = generate_track_by_focus(focus_pos_steps, travel_mm, step_size)

        if folder_name is None:
            folder_name = f"M2_Data_{w.serial}_{w.model}_{time.strftime('%Y-%m-%d_%H-%M-%S')}"

        raw_dir = os.path.join(folder_name, "raw")
        pgm_dir = os.path.join(folder_name, "pgm")
        analysis_dir = os.path.join(folder_name, "analysis")
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(pgm_dir, exist_ok=True)
        os.makedirs(analysis_dir, exist_ok=True)

        w.raw_dir = raw_dir

        cooler = CoolerData(axis_service.controller)
        meta_rows = []

        z_list, dx_list, dy_list = [], [], []

        for pos in track:
            if stop_flag():
                break

            try:
                axis_service.go_to(0, int(pos))
                if stop_flag():
                    break

                try:
                    df = cooler.get_dataframe()
                    if hasattr(df, "to_dict"):
                        meta_rows.append(df.to_dict(orient="records")[0] if len(df) else {})
                except Exception:
                    pass

                filename = (pos / step_size)  
                img, res = self.capture_save_measure(pos, filename, raw_dir, pgm_dir)
                if res is None:
                    continue

                dx_list.append(res.Dx_mm)
                dy_list.append(res.Dy_mm)
                z_list.append(pos / step_size)

            except Exception as e:
                if stop_flag():
                    break
                print(f"Scan error at pos {pos}: {e}")
                traceback.print_exc()

        meta_df = None
        try:
            meta_df = pd.DataFrame(meta_rows) if meta_rows else pd.DataFrame()
        except Exception:
            meta_df = None

        return folder_name, raw_dir, pgm_dir, z_list, dx_list, dy_list, meta_df

    def compute_m2(self, z_list, dx_list, dy_list, wavelength_nm, title=""):
        z = np.asarray(z_list, dtype=float) * 1e-3    
        dx = np.asarray(dx_list, dtype=float) * 0.001 
        dy = np.asarray(dy_list, dtype=float) * 0.001 
        lam = float(wavelength_nm) * 1e-9

        return compute_m2_hyperbola(
            z, dx, dy, lam,
            metric="1e2_diameter",
            z_window=(70.0, 135.0),
            min_points=8,
            return_fig=True,
            units="mm",
            title=title
        )

    def create_gif_async(self, folder_name):
        try:
            return create_gif_from_arrays(self.w.images_dict, folder_name)
        except Exception:
            traceback.print_exc()
            return None
