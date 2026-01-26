from PIL import Image
import numpy as np
import pickle
import os
import logging

import os
import sys
import pickle
import logging

class ImageSaturationProcessor:
    
    def __init__(self, pkl_file="saturation_data.pkl", intensity_threshold=100, active_pixel_channel=3):
        self.pkl_file = pkl_file  

        self.INTENSITY_THRESHOLD = intensity_threshold
        self.ACTIVE_PIXEL_CHANNEL = active_pixel_channel
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

        self.previous_saturation_level, self.previous_background_level = self._load_previous_values()

    def _load_previous_values(self):
        if os.path.exists(self.pkl_file):
            try:
                with open(self.pkl_file, 'rb') as f:
                    data = pickle.load(f)
                    previous_saturation_level = data.get('saturation_level', 0)
                    previous_background_level = data.get('background_level', 0)
                return previous_saturation_level, previous_background_level
            except Exception as e:
                self.logger.error(f"Error loading data from pickle file: {e}")
        
        return 0, 0
    def _save_values(self, saturation_level, background_level):

        try:
            data = {
                'saturation_level': saturation_level,
                'background_level': background_level
            }
            with open(self.pkl_file, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            self.logger.error(f"Error saving data to pickle file: {e}")
    
    def _calculate_saturation_level(self, pixel_intensity_sum, number_of_bright_pixels):
        if number_of_bright_pixels > 0:
            return pixel_intensity_sum // number_of_bright_pixels
        
        self.logger.info(f"No bright pixels, previous saturation value used: {self.previous_saturation_level}")
        return self.previous_saturation_level
    
    def _remove_background_from_pixel(self, pixel_val, background_level):

        result = pixel_val - background_level
        return max(0, result)
    
    def _find_background_level(self, histogram):

        histogram_integral = [0] * 256
        integral = 0
        
        for k in range(200):
            integral += histogram[k]
            histogram_integral[k] = integral
        
        peak = 0
        if histogram_integral[199] > 0:
            for k in range(200):
                if histogram_integral[k] > histogram_integral[199] / 2:
                    peak = k
                    break
        
        return peak
    
    def _adjust_measurement_range(self, measurement_range_x1, measurement_range_x2,
                                 measurement_range_y1, measurement_range_y2,
                                 height_in_pixels, width_in_pixels):

        measurement_range_x1 = max(0, measurement_range_x1)
        measurement_range_y1 = max(0, measurement_range_y1)
        measurement_range_x2 = min(height_in_pixels, measurement_range_x2)
        measurement_range_y2 = min(width_in_pixels, measurement_range_y2)

        if measurement_range_x1 == measurement_range_x2:
            measurement_range_x1 = 0
            measurement_range_x2 = height_in_pixels
        if measurement_range_y1 == measurement_range_y2:
            measurement_range_y1 = 0
            measurement_range_y2 = width_in_pixels
        if self.previous_saturation_level < 20:
            measurement_range_x1 = 0
            measurement_range_x2 = height_in_pixels
            measurement_range_y1 = 0
            measurement_range_y2 = width_in_pixels
        
        return measurement_range_x1, measurement_range_x2, measurement_range_y1, measurement_range_y2
    
    def process_image(self, image, 
                     measurement_range_x1=0, measurement_range_x2=0, 
                     measurement_range_y1=0, measurement_range_y2=0,
                     background_visible=True):
        original_is_pil = isinstance(image, Image.Image)
        original_mode = None
        
        if original_is_pil:
            original_mode = image.mode
            if image.mode != 'L':
                image = image.convert('L')
            image_data = np.array(image)
        else:
            image_data = image
        
        height, width = image_data.shape
        measurement_range_y1 *= self.ACTIVE_PIXEL_CHANNEL
        measurement_range_y2 *= self.ACTIVE_PIXEL_CHANNEL

        measurement_range_x1, measurement_range_x2, measurement_range_y1, measurement_range_y2 = self._adjust_measurement_range(
            measurement_range_x1, measurement_range_x2,
            measurement_range_y1, measurement_range_y2,
            height, width
        )

        histogram = [0] * 256
        pixel_intensity_sum = 0
        number_of_bright_pixels = 0
        processed_image_data = np.copy(image_data)
        
        for y in range(measurement_range_x1, measurement_range_x2):
            for x in range(measurement_range_y1, measurement_range_y2, self.ACTIVE_PIXEL_CHANNEL):
                if y < height and x < width:
                    pixel_value = int(image_data[y, x])
                    if background_visible:
                        processed_pixel = self._remove_background_from_pixel(pixel_value, self.previous_background_level)
                        processed_image_data[y, x] = processed_pixel
                        pixel_value = processed_pixel
                    if 0 < pixel_value < 255:
                        histogram[pixel_value] += 1
                    if pixel_value > self.INTENSITY_THRESHOLD:
                        pixel_intensity_sum += pixel_value
                        number_of_bright_pixels += 1
        
        saturation_level = self._calculate_saturation_level(pixel_intensity_sum, number_of_bright_pixels)
        background_level = self._find_background_level(histogram)
        self._save_values(saturation_level, background_level)
        if original_is_pil:
            processed_image = Image.fromarray(processed_image_data)
            if original_mode != 'L':
                processed_image = processed_image.convert(original_mode)
        else:
            processed_image = processed_image_data
        
        return int(saturation_level), background_level, processed_image
    
    def get_previous_values(self):
        return self.previous_saturation_level, self.previous_background_level
    
    def reset_values(self):

        self.previous_saturation_level = 0
        self.previous_background_level = 0
        self._save_values(0, 0)
        self.logger.info("Values restored to their original state")
