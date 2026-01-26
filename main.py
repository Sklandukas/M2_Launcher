import os
import json
import tkinter as tk
import traceback

from worker import CameraWorker
from ui.window import AppWindow

def create_default_config():
    if not os.path.exists("camera_config.json"):
        config = {
            "CameraDefaultSettings": {
                "width": 1288,
                "height": 964,
                "exposure_time": 1000,
                "gain": 0,
                "brightness": 1.367188,
                "frame_rate": 30,
                "serial_number": "16114212"  
            }
        }
        with open("camera_config.json", "w") as f:
            json.dump(config, f, indent=4)

if __name__ == "__main__":
    try:
        root = tk.Tk()
        root.title("Kameros ir ašies valdymas")
        root.geometry("1200x700")
        worker = CameraWorker("camera_config.json")

        app = AppWindow(root, worker)

        def on_close():
            print("Application closing...")
            try:
                worker.laser_auto_off()
            except Exception as e:
                traceback.print_exc()
            
            worker.stop()
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_close)

        if worker.run():
            try:
                root.mainloop()
            except KeyboardInterrupt:
                print("Stopping camera due to keyboard interrupt...")
            finally:
                try:
                    worker.laser_auto_off()
                except Exception as e:
                    print(f"Error turning off laser during keyboard interrupt: {e}")
                
                worker.stop()
        else:
            root.destroy()

    except Exception as ex:
        print(f"Error details: {traceback.format_exc()}")
