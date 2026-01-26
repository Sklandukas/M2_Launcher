
import numpy as np 
import traceback

def analyze_image(self, raw_image):
    try:            
        image_data = raw_image.GetData()
        
        image_array = np.array(image_data, dtype=np.uint8).reshape(
            (raw_image.GetHeight(), raw_image.GetWidth())
        )
        
        self.latest_frame = image_array.copy()
        
        saturation_level = np.max(image_array)
        
        background_level = int(np.percentile(image_array, 5))
        
        center_point = {
            "x": raw_image.GetWidth() // 2,
            "y": raw_image.GetHeight() // 2
        }
        
        return saturation_level , background_level, center_point
        
    except Exception as ex:
        print(f"Error analyzing image: {ex}")
        print(f"Error details: {traceback.format_exc()}")
        return 0, 0, {"x": 0, "y": 0}

# import cv2
# import numpy as np
# import traceback

# import numpy as np
# import traceback
# import time

# def analyze_image(self, raw_image):
#     start = time.time()   # startuojam laiką

#     H, W = raw_image.GetHeight(), raw_image.GetWidth()
#     arr = np.frombuffer(raw_image.GetData(), dtype=np.uint8)
#     gray = arr.reshape((H, W, 3)).max(axis=2) if arr.size == H*W*3 else arr.reshape((H, W))

#     background = float(np.percentile(gray, 5))
#     p95 = float(np.percentile(gray, 95))   # matas dėmei (10% area -> p90–p95 veikia gerai)
#     intensity = max(p95 - background, 0.0)

#     max_val = int(gray.max())
#     dtype_max = 255
#     clipped_fraction = float((gray >= dtype_max).mean())

#     self.latest_frame = gray.copy()
#     center_point = {"x": W // 2, "y": H // 2}

#     end = time.time()  # stabdom laiką
#     return intensity, background, center_point


# import numpy as np
# import PySpin

# def analyze_image(self, raw_image):
#     try:
#         if raw_image is None or (hasattr(raw_image, "IsIncomplete") and raw_image.IsIncomplete()):
#             stat = raw_image.GetImageStatus() if hasattr(raw_image, "GetImageStatus") else "unknown"
#             raise ValueError(f"Incomplete image. Status={stat}")

#         processor = PySpin.ImageProcessor()
#         processor.SetColorProcessing(PySpin.HQ_LINEAR)

#         # Mono8 kaip universalus pagrindas
#         img_conv = processor.Convert(raw_image, PySpin.PixelFormat_Mono8)
#         img = img_conv.GetNDArray()  # HxW np.ndarray

#         if img is None or img.size == 0:
#             raise ValueError("Empty NDArray from GetNDArray().")

#         H, W = img.shape[:2]
#         lumin = img.astype(np.float32)

#         max_possible = np.iinfo(img.dtype).max
#         background_level = float(np.percentile(lumin, 5))

#         # „saturation“ kaip max reikšmė (jei dar reikia)
#         saturation_level = int(lumin.max()) or 1

#         self.latest_frame = img.copy()
#         center_point = {"x": W // 2, "y": H // 2}
#         return saturation_level, int(background_level), center_point

#     except Exception as ex:
#         print(f"Error analyzing image: {ex}")
#         import traceback; print(f"Error details: {traceback.format_exc()}")
#         return 1, 0, {"x": 0, "y": 0}
#     finally:
#         # LABAI SVARBU: visuomet atleisti kadrą
#         try:
#             raw_image.Release()
#         except Exception:
#             pass
