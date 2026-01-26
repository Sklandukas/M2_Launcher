import numpy as np
import os
import tkinter as tk
from utils.ColorIm import convert_to_color_image
import matplotlib
matplotlib.use('Agg')  
import matplotlib.pyplot as plt
from matplotlib.animation import ArtistAnimation, PillowWriter
import traceback
from PIL import Image, ImageTk

def create_gif_from_arrays(data_dict, folder_name, interval=500, apply_color=True):
    try:
        gif_path = os.path.join(folder_name, f"{folder_name}.gif")

        fig, ax = plt.subplots()
        ax.set_axis_off()
        
        frames = []
        
        for key, array in data_dict.items():
            if array.dtype != np.uint8:
                array = ((array - array.min()) * (255.0 / (array.max() - array.min()))).astype(np.uint8)
            
            if apply_color:
                array = convert_to_color_image(array)
                
            frame = ax.imshow(array, animated=True)
            frames.append([frame])
        
        ani = ArtistAnimation(fig, frames, interval=interval, blit=True, repeat=True)
        
        writer = PillowWriter(fps=30)
        ani.save(gif_path, writer=writer)
        
        plt.close(fig)  
        
        print(f"GIF saved to: {gif_path}")
        return gif_path
        
    except Exception as e:
        print(f"Error creating GIF: {e}")
        print(traceback.format_exc())
        return None

def animate_gif(label, gif, showing_flag_getter):

    try:
        frames = []
        try:
            while True:
                current = gif.copy()
                
                label_width = label.winfo_width()
                label_height = label.winfo_height()
                
                if label_width > 1 and label_height > 1:
                    img_ratio = current.width / current.height
                    label_ratio = label_width / label_height
                    
                    if img_ratio > label_ratio:
                        new_width = label_width
                        new_height = int(label_width / img_ratio)
                    else:
                        new_height = label_height
                        new_width = int(label_height * img_ratio)
                    
                    current = current.resize((new_width, new_height), Image.LANCZOS)
                frames.append(ImageTk.PhotoImage(current))
                gif.seek(gif.tell() + 1)
        except EOFError:
            pass
        
        print(f"Loaded {len(frames)} frames from GIF")
            
        def update_frame(idx):
            if not showing_flag_getter():
                return
            
            frame = frames[idx]
            label.config(image=frame)
            label.image = frame 
            
            next_idx = (idx + 1) % len(frames)

            try:
                duration = gif.info.get('duration', 100)
            except:
                duration = 100
                
            label.after(duration, update_frame, next_idx)
        
        update_frame(0)
        
    except Exception as e:
        print(f"Error animating GIF: {e}")
        import traceback
        traceback.print_exc()

def store_gif(instance, gif_path):
    try:
        print(f"Storing GIF path: {gif_path}")
        instance.gif_path = gif_path

        if hasattr(instance, 'gif_button') and instance.gif_button is not None:
            instance.gif_button.config(state=tk.NORMAL)
            print("GIF button enabled")
    except Exception as e:
        print(f"Error storing GIF path: {e}")
        import traceback
        traceback.print_exc()