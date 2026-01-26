import tkinter as tk

class StorageUtilities:

    def store_figure(self, figure):
        self.measurement_figure = figure
        
        if hasattr(self, 'figure_button') and self.figure_button is not None:
            self.figure_button.config(state=tk.NORMAL)
        if hasattr(self, 'camera_button') and self.camera_button is not None:
            self.camera_button.config(state=tk.DISABLED)  
        
        if hasattr(self, 'save_data_button') and self.save_data_button is not None:
            self.save_data_button.config(state=tk.NORMAL)
        
        if hasattr(self, 'toggle_panel') and self.toggle_panel is not None:
            self.toggle_panel.pack(pady=5, fill=tk.X)
        if hasattr(self, 'save_data_button') and self.save_data_button is not None:
            self.save_data_button.config(state=tk.NORMAL)

