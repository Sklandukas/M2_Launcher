import os
import shutil
import traceback
import numpy as np

from storage.gif import store_gif
from utils.storage_utils import StorageUtilities

class StorageService:
    def __init__(self, worker):
        self.w = worker

    def save_figure_png(self, folder_name, fig, serial, model):
        if fig is None:
            return None
        path = os.path.join(folder_name, f"{serial}_{model}.png")
        fig.savefig(path, dpi=300, bbox_inches="tight")
        try:
            StorageUtilities.store_figure(self.w, fig)
        except Exception:
            pass
        return path

    def save_m2_txt(self, folder_name, z_list, dx_list, dy_list):
        # kaip tavo: z*100, dx*1000, dy*1000 (palieku)
        z = np.asarray(z_list, dtype=float) * 1e-3
        dx = np.asarray(dx_list, dtype=float) * 0.001
        dy = np.asarray(dy_list, dtype=float) * 0.001

        data = np.column_stack((z * 100, dx * 1000, dy * 1000))
        path = os.path.join(folder_name, "M2_data.txt")
        np.savetxt(path, data, fmt="%.6f", delimiter="\t", header="", comments="")
        return path

    def store_gif(self, gif_path):
        if gif_path and os.path.exists(gif_path):
            store_gif(self.w, gif_path)
            return True
        return False

    def copy_results_to_folder(self, save_directory, original_name, gif_path=None, fig=None):
        saved = []

        if gif_path and os.path.exists(gif_path):
            gif_save_path = os.path.join(save_directory, f"{original_name}.gif")
            try:
                shutil.copy2(gif_path, gif_save_path)
                saved.append(f"GIF: {os.path.basename(gif_save_path)}")
            except Exception:
                traceback.print_exc()
                # fallback manual copy
                try:
                    with open(gif_path, "rb") as src:
                        with open(gif_save_path, "wb") as dst:
                            dst.write(src.read())
                    saved.append(f"GIF: {os.path.basename(gif_save_path)}")
                except Exception:
                    traceback.print_exc()

        if fig is not None:
            png_save_path = os.path.join(save_directory, f"{original_name}.png")
            try:
                fig.savefig(png_save_path, dpi=300, bbox_inches="tight")
                saved.append(f"PNG: {os.path.basename(png_save_path)}")
            except Exception:
                traceback.print_exc()

        return saved
