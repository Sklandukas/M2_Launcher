import os
import tkinter as tk
import re

import tkinter.messagebox as messagebox
from tkinter import ttk, simpledialog
from smb.SMBConnection import SMBConnection
from config.logging_config import logger

class ExternalFileClient:
    SERVER_URL_PREFIX = "smb://"

    def __init__(self, username, password, shared_folder_name, client_name="client", server_name="server", serial_no=None):
        self.username = username
        self.password = password
        self.shared_folder_name = shared_folder_name
        self.conn = SMBConnection(username, password, client_name, server_name, use_ntlm_v2=True)
        self.find_folder = serial_no

    def connect(self, server_ip):
        try:
            connected = self.conn.connect(server_ip, 139)
            if connected:
                logger.info(f"Connected to SMB server: {server_ip}")
            else:
                logger.warning(f"Could not connect to SMB server: {server_ip}")
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            messagebox.showerror("Connection Error", f"Error while connecting to the server: {e}")
        return connected


    def close(self):
        if self.conn:
            self.conn.close()

    def list_directories(self, path="/"):

        if not self.conn:
            logger.warn("Not connected to the SMB server.")
            return []
        
        directories = []
        try:
            files = self.conn.listPath(self.shared_folder_name, path)
            for file in files:
                if file.isDirectory and file.filename not in ['.', '..']:
                    directories.append(file.filename)
            
            logger.info(f"Found {len(directories)} directories in '{path}'")
        except Exception as e:
            logger.error(f"Error listing directories: {e}")
        
        return directories
    
    def select_directory_dialog(self, path="/", title="Select folder", parent=None, manual=None):
        if not self.conn:
            logger.warning("Not connected to the SMB server.")
            messagebox.showerror("Connection Error", "Not connected to the SMB server.")
            return None
        
        directories = self.list_directories(path)
        selected_dir = None

        if manual is False:
            if self.find_folder:
                find_folder_cleaned = self.find_folder.strip()
                logger.info(f"Searching for folder: {find_folder_cleaned}")  
                found = False

                for x in directories:
                    if re.search(re.escape(find_folder_cleaned), x, re.IGNORECASE):
                        selected_dir = os.path.join(path, x)
                        logger.info(f"Found directory: {selected_dir}")
                        found = True
                        break

                if found:
                    logger.info(f"Directory '{find_folder_cleaned}' found and selected automatically.")
                    messagebox.showinfo("Directory Found", f"Directory '{find_folder_cleaned}' found and selected automatically.")
                    return selected_dir
                else:
                    logger.warning(f"Directory '{find_folder_cleaned}' not found.")
                    messagebox.showwarning("Directory Not Found", f"Directory '{find_folder_cleaned}' not found.")

        else:
            selected_dir = None
            temp_root = None
            if parent is None:
                temp_root = tk.Tk()
                temp_root.withdraw()  
                parent = temp_root
            
            dialog = tk.Toplevel(parent)
            dialog.title(title)
            dialog.geometry("400x300")
            dialog.transient(parent)  
            dialog.grab_set()  

            def on_select():
                nonlocal selected_dir  
                selected_index = directory_listbox.curselection()
                if selected_index:
                    selected_dir = os.path.join(path, directories[selected_index[0]])  
                    logger.info(f"Selected directory: {selected_dir}")
                    messagebox.showinfo("Directory Selected", f"Selected directory: {selected_dir}")
                dialog.destroy()

            def on_cancel():
                dialog.destroy()

            frame = ttk.Frame(dialog, padding="10")
            frame.pack(fill=tk.BOTH, expand=True)

            label = ttk.Label(frame, text=f"Folders '{path}':")
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

            select_button = ttk.Button(button_frame, text="Select", command=on_select)
            select_button.pack(side=tk.RIGHT, padx=(5, 0))

            cancel_button = ttk.Button(button_frame, text="Cancel", command=on_cancel)
            cancel_button.pack(side=tk.RIGHT)

            directory_listbox.bind("<Double-1>", lambda event: on_select())

            dialog.wait_window()

            if temp_root:
                temp_root.destroy()

            return selected_dir

    def find_in_directory(self, search_name, path="/"):
        if not self.conn:
            logger.warn("Not connected to the SMB server.")
            return None
        search_name_lower = search_name.lower()
        found_directories = []
        try:
            files = self.conn.listPath(self.shared_folder_name, path)
            for file in files:
                if file.isDirectory and search_name_lower in file.filename.lower():
                    found_directories.append(file.filename)
        except Exception as e:
            logger.error(f"Error searching directory: {e}")

        if not found_directories:
            logger.warning(f"No folders containing '{search_name}' were found.")
        else:
            logger.info(f"Folders containing '{search_name}': {found_directories}")
            if len(found_directories) > 1:
                logger.warning(f"More than one folder was found ({len(found_directories)}).")
        return found_directories[0] if found_directories else None

    def create_folder(self, parent_directory, new_folder_name):
        if not self.conn:
            logger.warn("Not connected to the SMB server.")
            return
        try:
            new_folder_path = os.path.join(parent_directory, new_folder_name)
            self.conn.createDirectory(self.shared_folder_name, new_folder_path)
            logger.info(f"Folder '{new_folder_name}' created in '{parent_directory}'.")
        except Exception as e:
            logger.error(f"Error creating folder: {e}")

    def upload_file(self, local_file_path, remote_directory, remote_file_name=None):
        if not self.conn:
            logger.warn("Not connected to the SMB server.")
            return
        if not os.path.exists(local_file_path):
            logger.error(f"Local file '{local_file_path}' does not exist.")
            return

        try:
            with open(local_file_path, 'rb') as file_obj:
                remote_file_name = remote_file_name or os.path.basename(local_file_path)
                remote_path = os.path.join(remote_directory, remote_file_name)
                self.conn.storeFile(self.shared_folder_name, remote_path, file_obj)
                logger.info(f"File '{local_file_path}' uploaded to '{remote_path}'.")
        except Exception as e:
            logger.error(f"Error uploading file: {e}")