import cv2
import numpy as np
from PIL import Image, ImageTk
from utils.ColorIm import convert_to_color_bitmap  # tavo modulis

def overlay_info(frame, exposure_us, saturation, background):
    
    cv2.putText(frame, f"Exposure: {exposure_us * 0.001:.1f} ms", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(frame, f"Saturation: {saturation}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(frame, f"Background: {background}", (10, 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    h, w = frame.shape[:2]
    cx, cy = w // 2, h // 2
    cv2.line(frame, (cx - 20, cy), (cx + 20, cy), (0, 0, 255), 2)
    cv2.line(frame, (cx, cy - 20), (cx, cy + 20), (0, 0, 255), 2)
    return frame

def prepare_for_tk(latest_frame: np.ndarray, label_width: int, label_height: int,
                   exposure_us: float, saturation: float, background: float):
    if latest_frame is None:
        return None

    frame = latest_frame.copy()
    frame = convert_to_color_bitmap(frame)

    if len(frame.shape) == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

    frame = overlay_info(frame, exposure_us, saturation, background)

    if label_width > 1 and label_height > 1:
        img_ratio = frame.shape[1] / frame.shape[0]
        label_ratio = label_width / label_height
        if img_ratio > label_ratio:
            new_w = label_width
            new_h = int(label_width / img_ratio)
        else:
            new_h = label_height
            new_w = int(label_height * img_ratio)
        frame = cv2.resize(frame, (new_w, new_h))

    img = Image.fromarray(frame)
    return ImageTk.PhotoImage(image=img)
