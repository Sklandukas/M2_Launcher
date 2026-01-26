import tkinter as tk
import json
import os

from tkinter import ttk, messagebox
from ExternalFileServer.ExternalFilerServerClientConnection import check_server_connection
from ExternalFileServer.erp.erp_connect import ErpNextApi

class SettingsDialog:

    def __init__(self, parent, serial_no=None, update_status_callback=None):
        self.parent = parent
        self.update_status_callback = update_status_callback  # Callback funkcija
        self.settings_window = tk.Toplevel(parent)
        self.settings_window.title("Settings")
        self.settings_window.geometry("400x450")
        self.settings_window.transient(parent)  
        self.settings_window.grab_set()  

        self.settings_window.minsize(400, 450)  
        self.main_frame = ttk.Frame(self.settings_window, padding="20")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.serial_no = serial_no
        self.settings = self.load_settings()
        self.selected_folder = tk.StringVar()
        self.selected_folder.set(self.settings.get("selected_folder", ""))

        self.erp_connected = False        
        self.create_widgets()

    def _create_input_row(self, label_text, row_num, var_name, default_value="", show=None):
        
        ttk.Label(self.main_frame, text=label_text).grid(row=row_num, column=0, sticky=tk.W, pady=5)
        
        entry = ttk.Entry(self.main_frame, width=30, textvariable=getattr(self, var_name, tk.StringVar()))
        if show:
            entry.config(show=show)
        
        entry.grid(row=row_num, column=1, sticky=tk.W, pady=5)
        entry.insert(0, default_value)
        
        setattr(self, var_name, entry)

        
    def create_widgets(self):
        title_label = ttk.Label(self.main_frame, text="Connection Settings", font=("Arial", 14, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20), sticky=tk.W)

        prod_section = ttk.Label(self.main_frame, text="Production Server", font=("Arial", 12))
        prod_section.grid(row=1, column=0, columnspan=2, pady=(0, 10), sticky=tk.W)

        ttk.Label(self.main_frame, text="Selected Folder:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self._create_input_row("Username:", 2, "prod_username", self.settings.get("prod_username", ""))
        self._create_input_row("Password:", 3, "prod_password", self.settings.get("prod_password", ""), show="*")

        self.folder_entry = ttk.Entry(self.main_frame, width=25, textvariable=self.selected_folder)
        self.folder_entry.grid(row=5, column=1, sticky=tk.W, pady=5)
        self.folder_entry.config(state="normal")

        self.browse_manual = ttk.Button(self.main_frame, text="Browse", command=self.select_folder_manual)
        self.browse_manual.grid(row=5, column=1, sticky=tk.E, pady=5)

        erp_section = ttk.Label(self.main_frame, text="ERP Server", font=("Arial", 12))
        erp_section.grid(row=6, column=0, columnspan=2, pady=(15, 10), sticky=tk.W)

        self._create_input_row("Username:", 7, "erp_username", self.settings.get("erp_username", ""))
        self._create_input_row("Password:", 8, "erp_password", self.settings.get("erp_password", ""), show="*")

        self._create_input_row("Delay time:", 9, "delay_time", self.settings.get("delay_time", ""))  
        button_frame = ttk.Frame(self.main_frame)
        button_frame.grid(row=10, column=0, columnspan=2, pady=(20, 0), sticky=tk.E)

        ttk.Button(button_frame, text="Cancel", command=self.settings_window.destroy).pack(side=tk.RIGHT, padx=(5, 0))
        # ttk.Button(button_frame, text="Save", command=self.save_settings).pack(side=tk.RIGHT)
        ttk.Button(button_frame, text="Test", command=self.test_connection).pack(side=tk.RIGHT)

        self.main_frame.columnconfigure(1, weight=1)
        self.main_frame.rowconfigure(10, weight=1)

    def test_param(self):
        self.connect_to_production()
        self.connect_to_erp()

    def test_connection(self):
        self.test_successful = False
        self.erp_connected = False
        self.connect_to_production()
        self.connect_to_erp()

        if self.test_successful and self.erp_connected:
            messagebox.showinfo("Connection Status", "Successfully connected to both the server and ERP system!")
            if self.update_status_callback:
                self.update_status_callback(True)  
            self.save_settings()
            return True
        else:
            messagebox.showerror("Connection Error", "Failed to connect to one or both servers.")
            if self.update_status_callback:
                self.update_status_callback(False)  
            self.save_settings()
            return False
        
    def connect_to_production(self):
        username = self.prod_username.get()
        password = self.prod_password.get()

        if not username:
            messagebox.showwarning("Connection Error", "Įveskite vartotojo vardą")
            return

        if not password:
            messagebox.showwarning("Connection Error", "Įveskite slaptažodį")
            return

        try:
            self.file_client = check_server_connection(username, password, self.serial_no)

            if self.file_client:
                self.test_successful = True
                
                self.folder_entry.config(state="normal")
                self.browse_manual.config(state="normal")

        except Exception as e:
            messagebox.showerror("Connection Error", f"Could not connect to the server: {e}")


    def connect_to_erp(self):
        username = self.erp_username.get()
        password = self.erp_password.get()

        if not username:
            messagebox.showwarning("Connection Error", "Įveskite ERP vartotojo vardą")
            return

        if not password:
            messagebox.showwarning("Connection Error", "Įveskite ERP slaptažodį")
            return

        try:
            erp_api = ErpNextApi(username=username, password=password, serial_no = "000123")
            login_erp = erp_api.connect()

            serial_data = erp_api.get_serial_no_data()

            if serial_data:
                print("Gauti duomenys:", serial_data)
            else:
                print("Nepavyko gauti duomenų.")

            if serial_data:
                self.erp_connected = True
            else:
                messagebox.showerror("Connection Error", "Unable to connect to the ERP server.")
        except Exception as e:
            messagebox.showerror("Connection Error", f"Could not connect to the ERP server: {e}")
    
    def select_folder_manual(self):        
        if self.file_client:
            try:
                print("Calling select_directory_dialog method...")  
                selected_dir = self.file_client.select_directory_dialog(
                    title="Select folder", 
                    parent=self.settings_window,
                    manual=True
                )
                print(f"Method manual returned: {selected_dir}")  

                if selected_dir:
                    print(f"Folder selected: {selected_dir}")
                    self.folder_entry.config(state="normal")
                    self.folder_entry.delete(0, tk.END)
                    self.folder_entry.insert(0, selected_dir)
                    self.selected_folder.set(selected_dir)
                    self.folder_entry.config(state="disabled") 
                    messagebox.showinfo("Information", f"Selected folder: {selected_dir}")
                else:
                    print("No folder selected.")
                    messagebox.showinfo("Information", "No folder has been selected.")
            except Exception as e:
                print(f"Exception occurred: {str(e)}")  
                messagebox.showerror("Error", f"Unable to open the folder selection dialog: {e}")
        else:
            print("File client is None, cannot select folder")

    def select_folder(self):        
        if self.file_client:
            try:
                print("Calling select_directory_dialog method...")  
                selected_dir = self.file_client.select_directory_dialog(
                    title="Select folder", 
                    parent=self.settings_window,
                    manual=True
                )
                print(f"Method returned: {selected_dir}")  

                if selected_dir:
                    self.folder_entry.config(state="normal")
                    self.folder_entry.delete(0, tk.END)
                    self.folder_entry.insert(0, selected_dir)
                    self.selected_folder.set(selected_dir)
                    self.folder_entry.config(state="disabled") 
                    print(f"Selected directory set to: {self.selected_folder.get()}")  
                    messagebox.showinfo("Information", f"Selected folder: {selected_dir}")
                else:
                    print("No directory was selected or returned")  
                    messagebox.showinfo("Information", "No folder has been selected.")
            except Exception as e:
                print(f"Exception occurred: {str(e)}")  
                messagebox.showerror("Error", f"Unable to open the folder selection dialog: {e}")
        else:
            print("File client is None, cannot select folder")
    
    def save_settings(self):
        settings = {
            "prod_username": self.prod_username.get(),
            "prod_password": self.prod_password.get(),
            "erp_username": self.erp_username.get(),
            "erp_password": self.erp_password.get(),
            "delay_time" : self.delay_time.get(),
            "selected_folder": self.selected_folder.get()  
        }
        
        try:
            config_dir = os.path.join(os.path.expanduser("~"), ".matchbox_config")
            os.makedirs(config_dir, exist_ok=True)
            
            with open(os.path.join(config_dir, "settings.json"), "w") as f:
                json.dump(settings, f)
                
        except Exception as e:
            messagebox.showerror("Error", f"Could not save settings: {e}")
    
    def load_settings(self):
        try:
            config_file = os.path.join(os.path.expanduser("~"), ".matchbox_config", "settings.json")
            if os.path.exists(config_file):
                with open(config_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Could not load settings: {e}")
        return {}

def get_settings():
    try:
        config_file = os.path.join(os.path.expanduser("~"), ".matchbox_config", "settings.json")
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"Could not load settings: {e}")
    return {}