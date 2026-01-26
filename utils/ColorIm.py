import numpy as np
from PIL import Image

def convert_to_color_image(processed_image):
    try:
        if processed_image is None:
            return None
            
        grayscale_array = np.asarray(processed_image)  
        if grayscale_array.size == 0:
            return None

        r = np.zeros(256, dtype=np.uint8)
        g = np.zeros(256, dtype=np.uint8)
        b = np.zeros(256, dtype=np.uint8)
        
        indices = np.arange(256)
        
        mask_b1 = indices < 33
        b[mask_b1] = np.minimum(indices[mask_b1] * 7, 255)
        
        mask_g1 = (33 <= indices) & (indices < 97)
        g[mask_g1] = np.minimum(indices[mask_g1] * 4 - 129, 255)
        b[33:97] = 255
        
        mask_rgb = (97 <= indices) & (indices < 161)
        r[mask_rgb] = np.minimum(indices[mask_rgb] * 4 - 386, 255)
        g[97:161] = 255
        b[mask_rgb] = np.minimum(-4 * indices[mask_rgb] + 640, 255)
        
        mask_rg = (161 <= indices) & (indices < 225)
        r[161:225] = 255
        g[mask_rg] = np.minimum(-4 * indices[mask_rg] + 896, 255)
        
        mask_rb = indices >= 225
        r[225:256] = 255
        b[mask_rb] = np.minimum(4 * indices[mask_rb] - 896, 255)

        color_array = np.empty((*grayscale_array.shape, 3), dtype=np.uint8)
        
        color_array[..., 0] = r[grayscale_array]
        color_array[..., 1] = g[grayscale_array]
        color_array[..., 2] = b[grayscale_array]

        return Image.fromarray(color_array)

    except Exception as e:
        print(f"Color conversion error: {e}")
        return None
    
import numpy as np

def convert_to_color_bitmap(processed_image):
    try:
        if processed_image is None:
            return None
        grayscale_array = np.asarray(processed_image)
        if grayscale_array.size == 0:
            return None

        r = np.zeros(256, dtype=np.uint8)
        g = np.zeros(256, dtype=np.uint8)
        b = np.zeros(256, dtype=np.uint8)
        
        indices = np.arange(256)
        
        mask_b1 = indices < 33
        b[mask_b1] = np.minimum(indices[mask_b1] * 7, 255)
        
        mask_g1 = (33 <= indices) & (indices < 97)
        g[mask_g1] = np.minimum(indices[mask_g1] * 4 - 129, 255)
        b[33:97] = 255
        
        mask_rgb = (97 <= indices) & (indices < 161)
        r[mask_rgb] = np.minimum(indices[mask_rgb] * 4 - 386, 255)
        g[97:161] = 255
        b[mask_rgb] = np.minimum(-4 * indices[mask_rgb] + 640, 255)
        
        mask_rg = (161 <= indices) & (indices < 200)
        r[161:225] = 255
        g[mask_rg] = np.minimum(-4 * indices[mask_rg] + 896, 255)
        
        mask_rb = indices >= 200
        r[225:256] = 200
        b[mask_rb] = np.minimum(4 * indices[mask_rb] - 896, 255)

        color_array = np.empty((*grayscale_array.shape, 3), dtype=np.uint8)
        
        color_array[..., 0] = np.minimum(r[grayscale_array], 100)  
        color_array[..., 1] = np.minimum(g[grayscale_array] * 0.9, 255)  
        color_array[..., 2] = np.minimum(b[grayscale_array] * 0.7, 255)  

        return color_array

    except Exception as e:
        print(f"Spalvų konversijos klaida: {e}")
        return None
