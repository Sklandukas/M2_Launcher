import os
import time
import matplotlib.pyplot as plt
import numpy as np
import traceback
import tkinter as tk
from tkinter import ttk, messagebox
from ui.SettingsWindow import SettingsDialog, get_settings
from ExternalFileServer.ExternalFilerServerClientConnection import (get_smb_client, check_server_connection)

class AppWindow:
    def __init__(self, root, camera_worker):
        self.root = root
        self.camera_worker = camera_worker

        self.root.title("Camera and Axis Control")
        self.root.geometry("1200x700")

        self._init_gui()
        self._connect_camera_worker()
        self._auto_test_connection()

        # automatinis prisijungimas prie ašies kai tik langas sukurtas
        try:
            self.camera_worker.connect_to_axis()
        except Exception as e:
            print("Axis auto-connect failed:", e)

        self.root.bind("<Configure>", self.on_resize)

    def _init_gui(self):
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.camera_frame = tk.Frame(self.main_frame, bd=2, relief=tk.SUNKEN, width=800, height=600)
        self.camera_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.camera_frame.pack_propagate(False)

        self.camera_label = tk.Label(self.camera_frame, bg="black", text="Camera feed loading...")
        self.camera_label.pack(fill=tk.BOTH, expand=True)

        self.control_frame = tk.Frame(self.main_frame, padx=10, pady=10, width=250)
        self.control_frame.pack(side=tk.RIGHT, fill=tk.Y, expand=False)
        self.control_frame.pack_propagate(False)

        self.title_label = tk.Label(self.control_frame, text="Camera and Axis Control", font=("Arial", 14, "bold"))
        self.title_label.pack(pady=(0, 20))

        self.stop_button = tk.Button(
            self.control_frame, text="STOP", state=tk.DISABLED,
            bg="red", fg="white", width=20, height=2, font=("Arial", 12, "bold")
        )
        self.stop_button.pack(pady=5, fill=tk.X)

        # ašių / lazerio zona (be "Connect to Axis" mygtuko)
        self.axis_frame = tk.Frame(self.control_frame)
        self.axis_frame.pack(pady=5, fill=tk.X)

        self.laser_button = tk.Button(
            self.axis_frame, text="Turn ON Laser",
            bg="green", fg="white", width=20, height=2, font=("Arial", 10),
            command=self.camera_worker.toggle_laser
        )
        self.laser_button.pack(pady=5, fill=tk.X)

        self.axis_status_label = tk.Label(
            self.control_frame, text="Not Connected",
            font=("Arial", 12), bg="lightgray", width=25, pady=5
        )
        self.axis_status_label.pack(pady=10, fill=tk.X)

        self.operation_frame = tk.Frame(self.control_frame)
        self.operation_frame.pack(pady=5, fill=tk.X)

        self.test_button = tk.Button(
            self.operation_frame, text="Test Axis", state=tk.NORMAL,
            bg="blue", fg="white", width=20, height=2, font=("Arial", 10)
        )
        self.test_button.pack(pady=5, fill=tk.X)

        self.focus_button = tk.Button(
            self.operation_frame, text="Find the focus", state=tk.DISABLED,
            bg="green", fg="white", width=20, height=2, font=("Arial", 12, "bold")
        )
        self.focus_button.pack(pady=5, fill=tk.X)

        self.start_button = tk.Button(
            self.operation_frame, text="START", state=tk.NORMAL,
            bg="green", fg="white", width=20, height=2, font=("Arial", 12, "bold")
        )
        self.start_button.pack(pady=5, fill=tk.X)

        self.handmode_button = tk.Button(
            self.operation_frame, text = "Measurements from photos", state = tk.NORMAL,
            bg = "green", fg = "white", width = 20, height = 2, font = ("Arial", 12, "bold")
        )
        self.handmode_button.pack(pady=5, fill=tk.X)

        self.settings_button = tk.Button(
            self.operation_frame, text="Settings", state=tk.NORMAL,
            bg="gray", fg="white", width=20, height=2, font=("Arial", 10),
            command=self.open_settings_dialog
        )
        self.settings_button.pack(pady=5, fill=tk.X)

        ttk.Separator(self.control_frame, orient='horizontal').pack(fill=tk.X, pady=10)

        self.utils_frame = tk.Frame(self.control_frame)
        self.utils_frame.pack(pady=5, fill=tk.X)

        self.save_frame_button = tk.Button(
            self.utils_frame, text="Save Frame",
            bg="gray", fg="white", width=20, height=1
        )
        self.save_frame_button.pack(pady=5, fill=tk.X)

        self.toggle_panel = tk.Frame(self.control_frame)
        self.toggle_panel.pack(fill=tk.X)

        self.toggle_label = tk.Label(self.toggle_panel, text="View Toggle:", font=("Arial", 10, "bold"))
        self.toggle_label.pack(pady=(10, 5), anchor=tk.W)

        self.toggle_row1 = tk.Frame(self.toggle_panel)
        self.toggle_row1.pack(fill=tk.X, pady=(0, 2))

        self.figure_button = tk.Button(
            self.toggle_row1, text="Show Figure",
            bg="purple", fg="white", width=10, height=1, state=tk.DISABLED
        )
        self.figure_button.pack(side=tk.LEFT, padx=(0, 2), fill=tk.X, expand=True)

        self.camera_button = tk.Button(
            self.toggle_row1, text="Show Camera",
            bg="blue", fg="white", width=10, height=1, state=tk.DISABLED
        )
        self.camera_button.pack(side=tk.RIGHT, padx=(2, 0), fill=tk.X, expand=True)

        self.toggle_row2 = tk.Frame(self.toggle_panel)
        self.toggle_row2.pack(fill=tk.X, pady=(2, 0))

        self.gif_button = tk.Button(
            self.toggle_row2, text="Show GIF",
            bg="orange", fg="white", width=10, height=1, state=tk.DISABLED
        )
        self.gif_button.pack(side=tk.LEFT, padx=(0, 2), fill=tk.X, expand=True)

        self.save_data_button = tk.Button(
            self.toggle_row2, text="Save Data",
            bg="green", fg="white", width=10, height=1,
            command=self.save_to_smb
        )
        self.save_data_button.pack(side=tk.RIGHT, padx=(2, 0), fill=tk.X, expand=True)

        self.take_photo_button = tk.Button(
            self.toggle_row2,
            text="Take a photo",
            bg="green",
            fg="white",
            width=10,
            height=1,
            command=self.open_take_photo_dialog 
        )

        self.take_photo_button.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        self.status_label = tk.Label(self.root, text="", font=("Arial", 8), anchor="e")
        self.status_label.place(relx=0.95, rely=0.98, anchor="se")
        self.update_status_label()

    def _connect_camera_worker(self):
        self.test_button.config(command=self.camera_worker.test_axis)
        self.focus_button.config(command=self.camera_worker.find_focus_process)
        self.start_button.config(command=self.show_input_dialog)
        self.stop_button.config(command=self.camera_worker.stop_process)
        self.handmode_button.config(command=self.camera_worker.hand_mode)
        self.save_frame_button.config(command=self.camera_worker.save_current_frame)
        self.camera_worker.take_photo_button = self.take_photo_button

        self.camera_worker.test_button = self.test_button
        self.camera_worker.focus_button = self.focus_button
        self.camera_worker.start_button = self.start_button
        self.camera_worker.stop_button = self.stop_button
        self.camera_worker.axis_status_label = self.axis_status_label
        self.camera_worker.camera_label = self.camera_label

        self.camera_worker.handmode_button = self.handmode_button

        self.camera_worker.toggle_panel = self.toggle_panel
        self.camera_worker.figure_button = self.figure_button
        self.camera_worker.camera_button = self.camera_button
        self.camera_worker.gif_button = self.gif_button
        self.camera_worker.save_data_button = self.save_data_button
        self.camera_worker.laser_button = self.laser_button

        self.figure_button.config(command=self.camera_worker.show_figure)
        self.camera_button.config(command=self.camera_worker.show_camera)
        self.gif_button.config(command=self.camera_worker.show_gif)

    def _auto_test_connection(self):
        settings_dialog = SettingsDialog(parent=self.root, update_status_callback=self.update_status_label)
        success = settings_dialog.test_connection()
        self.update_status_label(bool(success))

    def open_settings_dialog(self):
        self.settings_dialog = SettingsDialog(parent=self.root, update_status_callback=self.update_status_label)
        self.settings_dialog.settings_window.deiconify()

    def update_status_label(self, status=None):
        if status is None: 
            self.status_label.config(text="Checking Connection...", fg="blue")
        elif status:
            self.status_label.config(text="Connected Successfully", fg="green")
        else:
            self.status_label.config(text="Connection Failed", fg="red")

    def on_resize(self, event):
        min_font_size = 6
        max_font_size = 14
        font_size = int(event.height / 100)
        font_size = max(min_font_size, min(font_size, max_font_size))
        self.status_label.config(font=("Arial", font_size))

    def show_input_dialog(self):
        try:
            self.camera_worker.start_process()
        except Exception as e:
            messagebox.showerror("Process Error", f"Could not start process: {e}")
            traceback.print_exc()

    def open_take_photo_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Photo name")
        dlg.geometry("350x160")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="Įveskite nuotraukos pavadinimą:").pack(pady=(12, 4))

        var = tk.StringVar()
        entry = ttk.Entry(dlg, textvariable=var, justify="center")
        entry.pack(padx=12, fill=tk.X)
        entry.focus_set()

        msg = ttk.Label(dlg, text="", foreground="red")
        msg.pack(pady=(6, 0))

        btns = ttk.Frame(dlg)
        btns.pack(pady=12, fill=tk.X)

        def on_ok():
            name = var.get().strip()
            if not name:
                msg.config(text="Pavadinimas negali būti tuščias")
                return

            dlg.destroy()
            self.camera_worker.take_photo(name)

        def on_cancel():
            dlg.destroy()

        ok_btn = ttk.Button(btns, text="OK", command=on_ok)
        ok_btn.pack(side=tk.RIGHT, padx=(6, 12))
        cancel_btn = ttk.Button(btns, text="Cancel", command=on_cancel)
        cancel_btn.pack(side=tk.RIGHT)

        dlg.bind("<Return>", lambda e: on_ok())
        dlg.bind("<Escape>", lambda e: on_cancel())

    def test_axis_callback(self):
        self.camera_worker.start_process()

    def _get_smb_client(self):
        smb_client = get_smb_client()
        if not smb_client or not hasattr(smb_client, "is_connected") or not smb_client.is_connected():
            settings = get_settings()
            username = settings.get("prod_username", "")
            password = settings.get("prod_password", "")
            if not username or not password:
                messagebox.showerror("SMB Error", "No login credentials identified. Check your settings.")
                return None
            smb_client = check_server_connection(username, password, self.camera_worker.serial_number)
            if not smb_client:
                messagebox.showerror("SMB Error", "Unable to connect to the SMB server. Check your settings.")
                return None
        return smb_client

    def simple_directory_dialog(self, directories):
        dialog = tk.Toplevel(self.root)
        dialog.title("Select the SMB folder for saving")
        dialog.geometry("400x300")
        dialog.grab_set()

        selected_dir = [None]

        def on_select():
            selected_index = directory_listbox.curselection()
            if selected_index:
                selected_dir[0] = directories[selected_index[0]]
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        frame = ttk.Frame(dialog, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        label = ttk.Label(frame, text="Select folder:")
        label.pack(anchor=tk.W, pady=(0, 5))

        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        directory_listbox = tk.Listbox(frame, yscrollcommand=scrollbar.set)
        directory_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=directory_listbox.yview)

        for directory in directories:
            directory_listbox.insert(tk.END, directory)

        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        select_button = ttk.Button(button_frame, text="Choose", command=on_select)
        select_button.pack(side=tk.RIGHT, padx=(5, 0))

        cancel_button = ttk.Button(button_frame, text="Cancel", command=on_cancel)
        cancel_button.pack(side=tk.RIGHT)

        directory_listbox.bind("<Double-1>", lambda event: on_select())
        self.root.wait_window(dialog)
        return selected_dir[0]

    def _get_selected_directory(self, smb_client):
        settings = get_settings()
        selected_directory = settings.get("selected_folder")

        if not selected_directory:
            try:
                directories = smb_client.list_directories()
                if not directories:
                    messagebox.showwarning("Warning", "No folders found on the SMB server.")
                    return None
                selected_directory = self.simple_directory_dialog(directories)
            except Exception as e:
                print(f"Error getting a list of folders: {e}")
                messagebox.showerror("SMB Error", f"Error getting a list of folders: {e}")
                return None

        if not selected_directory:
            messagebox.showinfo("Information", "Folder not selected. Files not saved.")
        return selected_directory

    def _create_new_folder(self, smb_client, parent_directory, folder_name):
        new_folder_path = f"{parent_directory}/{folder_name}"
        try:
            if hasattr(smb_client, "directory_exists") and not smb_client.directory_exists(new_folder_path):
                if hasattr(smb_client, "create_folder"):
                    smb_client.create_folder(parent_directory=parent_directory, new_folder_name=folder_name)
                else:
                    messagebox.showerror("SMB Error", "SMB client does not support folder creation.")
                    return None
        except Exception as e:
            print(f"Error creating new directory: {e}")
            messagebox.showerror("SMB Error", f"Error creating new directory: {e}")
            return None
        return new_folder_path

    def _upload_files(self, smb_client, new_folder_path):
        uploaded_files = []
        file_paths = [
            (getattr(self.camera_worker, "gif_path", None), "GIF"),
            (getattr(self.camera_worker, "figure_path", None), "Figure"),
        ]

        for file_path, file_type in file_paths:
            if file_path and os.path.exists(file_path):
                file_name = os.path.basename(file_path)
                try:
                    print(f"Uploading {file_type}: {file_path} → {new_folder_path}/{file_name}")
                    smb_client.upload_file(file_path, new_folder_path, file_name)
                    uploaded_files.append(file_name)
                except Exception as e:
                    print(f"Error uploading {file_type.lower()} file: {e}")
                    messagebox.showerror("SMB Error", f"Error uploading {file_type.lower()} file: {e}")
        return uploaded_files

    def _upload_txt_files(self, smb_client, new_folder_path):
        txt_name = "data_results"
        work_path = os.getcwd()
        try:
            for root_, _, files in os.walk(work_path):
                for file in files:
                    if file.endswith(".txt") and txt_name in file:
                        txt_path = os.path.join(root_, file)
                        print(f"Uploading: {txt_path} → {new_folder_path}/{file}")
                        smb_client.upload_file(txt_path, new_folder_path, file)
        except Exception as e:
            print(f"Error uploading txt files: {e}")
            messagebox.showerror("SMB Error", f"Error uploading txt files: {e}")

    def _upload_csv_file(self, smb_client, new_folder_path):
        key = "meta_data"
        work_path = os.getcwd()
        try:
            for root_, _, files in os.walk(work_path):
                for file in files:
                    if file.endswith(".csv") and key in file:
                        csv_path = os.path.join(root_, file)
                        print(f"Uploading: {csv_path} → {new_folder_path}/{file}")
                        smb_client.upload_file(csv_path, new_folder_path, file)
        except Exception as e:
            print(f"Error uploading csv: {e}")
            messagebox.showerror("SMB Error", f"Error uploading csv: {e}")

    def _convert_and_save_raw_files(self, smb_client, new_folder_path):
        raw_files_folder = f"{new_folder_path}/raw files"

        if self._create_new_folder(smb_client, new_folder_path, "raw files") is None:
            return

        images_dict = getattr(self.camera_worker, "images_dict", None)
        if not isinstance(images_dict, dict):
            print("No image data found in camera_worker.images_dict")
            return

        try:
            for file_name, image_array in images_dict.items():
                if isinstance(image_array, np.ndarray):
                    raw_file_name = f"{file_name}.raw"
                    raw_file_path = os.path.join(os.getcwd(), raw_file_name)

                    with open(raw_file_path, "wb") as raw_file:
                        raw_file.write(image_array.tobytes())

                    smb_client.upload_file(raw_file_path, raw_files_folder, raw_file_name)
                    os.remove(raw_file_path)
                else:
                    print(f"Skipping {file_name}: not a numpy array")
        except Exception as e:
            print(f"Error converting or uploading raw files: {e}")
            messagebox.showerror("SMB Error", f"Error converting or uploading raw files: {e}")

    def _get_figure(self):
        fig = None
        try:
            fig = plt.gcf()
            if not fig.get_axes():
                fig = None
        except Exception as e:
            print(f"Error getting current figure: {e}")

        if fig is None:
            if hasattr(self.camera_worker, "measurement_figure") and self.camera_worker.measurement_figure is not None:
                fig = self.camera_worker.measurement_figure
            elif hasattr(self.camera_worker, "figure"):
                fig = self.camera_worker.figure
            elif hasattr(self.camera_worker, "get_figure"):
                try:
                    fig = self.camera_worker.get_figure()
                except Exception:
                    fig = None
        return fig

    def _show_upload_success(self, folder_path, files):
        files_text = "\n".join(files)
        messagebox.showinfo(
            "Upload Successful",
            f"Files were uploaded to:\n{folder_path}\n\nUploaded:\n{files_text}"
        )

    def save_to_smb(self):
        try:
            if hasattr(self.camera_worker, "show_figure"):
                try:
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    save_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "saved_data")
                    print(f"save dir: {save_dir}")
                    os.makedirs(save_dir, exist_ok=True)

                    fig = self._get_figure()
                    if fig is not None:
                        figure_path = os.path.join(save_dir, f"M2_Graph_{timestamp}.png")
                        fig.savefig(figure_path, format="png", dpi=300)
                        self.camera_worker.figure_path = figure_path
                    else:
                        print("No valid figure to save")
                except Exception as e:
                    print(f"Error saving figure: {e}")
                    traceback.print_exc()

            smb_client = self._get_smb_client()
            if not smb_client:
                messagebox.showerror("SMB Error", "Unable to connect to the SMB server. Check your settings.")
                return

            selected_directory = self._get_selected_directory(smb_client)
            if not selected_directory:
                return

            folder_name = f"M2 Data_{self.camera_worker.serial_number}_{self.camera_worker.model}"
            new_folder_path = self._create_new_folder(smb_client, selected_directory, folder_name)
            if not new_folder_path:
                return

            uploaded_files = self._upload_files(smb_client, new_folder_path)
            if uploaded_files:
                self._show_upload_success(new_folder_path, uploaded_files)
            else:
                messagebox.showwarning("Warning", "Could not save any files.")

            self._upload_txt_files(smb_client, new_folder_path)
            self._upload_csv_file(smb_client, new_folder_path)
            self._convert_and_save_raw_files(smb_client, new_folder_path)

        except Exception as e:
            print(f"Error saving files to SMB: {e}")
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to save files to SMB: {e}")
