import os
import re
import numpy as np
import cv2
import tkinter as tk
import tkinter.messagebox as messagebox
from tkinter import filedialog
from .tk_utils import ui_call

def read_data_folder(folder: str):

    exts = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".pgm", ".npy")
    items = {}
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith(exts):
            continue
        path = os.path.join(folder, name)

        m = re.search(r"(-?\d+(\.\d+)?)", name)
        if not m:
            continue
        z = float(m.group(1))

        if name.lower().endswith(".npy"):
            arr = np.load(path)
        else:
            arr = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            if arr is None:
                continue
            if arr.ndim == 3:
                arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)

        items[z] = arr
    return items

def hand_mode_dialog(owner, initial_wavelength=None):
    parent = getattr(owner, "root", None) or getattr(owner, "master", None) or owner

    dlg = tk.Toplevel(parent)
    dlg.title("Rankiniai matavimai")
    dlg.geometry("450x250")
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(False, False)

    tk.Label(dlg, text="Įveskite bangos ilgį (nm):", font=("Arial", 11)).pack(padx=15, pady=(15, 5))

    wavelength_var = tk.StringVar()
    if initial_wavelength is not None:
        wavelength_var.set(str(initial_wavelength))

    wavelength_entry = tk.Entry(dlg, textvariable=wavelength_var, justify="center", font=("Arial", 11))
    wavelength_entry.pack(fill=tk.X, padx=15)
    wavelength_entry.focus_set()

    tk.Label(dlg, text="Nuotraukų folderis:", font=("Arial", 11)).pack(padx=15, pady=(15, 5))

    folder_var = tk.StringVar(value="Folderis nepasirinktas")
    folder_label = tk.Label(dlg, textvariable=folder_var, fg="blue", wraplength=400, justify="left")
    folder_label.pack(padx=15)

    def choose_folder():
        folder = filedialog.askdirectory(parent=dlg, title="Pasirinkite folderį su nuotraukomis")
        if folder:
            folder_var.set(folder)

    tk.Button(dlg, text="Pasirinkti folderį", command=choose_folder).pack(pady=(5, 10))

    result = {"lam": None, "folder": None}

    def on_ok():
        value = wavelength_var.get().strip()
        try:
            lam = float(value)
            if lam <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Neteisinga reikšmė", f"„{value}“ nėra tinkamas bangos ilgis.")
            return

        folder = folder_var.get()
        if folder == "Folderis nepasirinktas":
            messagebox.showwarning("Folderis nepasirinktas", "Prašau pasirinkti folderį su nuotraukomis.")
            return

        result["lam"] = lam
        result["folder"] = folder
        dlg.destroy()

    btn_frame = tk.Frame(dlg)
    btn_frame.pack(pady=10)

    tk.Button(btn_frame, text="OK", width=12, command=on_ok).pack(side=tk.LEFT, padx=10)
    tk.Button(btn_frame, text="Cancel", width=12, command=dlg.destroy).pack(side=tk.LEFT, padx=10)

    dlg.wait_window()
    return result["lam"], result["folder"]
