import PySpin
import time
import traceback

from utils.analysis_utils import analyze_image
from devices.camera.camera_settings import update_camera_settings

def camera_worker_task(instance, cam):
    try:
        cam.BeginAcquisition()
        
        while instance.running:
            try:
                raw_image = cam.GetNextImage(2000)  
                
                if raw_image.IsIncomplete():
                    print(f"Image incomplete with status {raw_image.GetImageStatus()}")
                else:
                    instance.frame_count += 1
                    if instance.frame_count % 10 == 0:
                        current_time = time.time()
            
                        instance.start_time = current_time
                    
                    saturation_level, background_level, center_point = analyze_image(instance, raw_image)
                    update_camera_settings(instance, cam, saturation_level, background_level)
                    
                    instance.previous_saturation_level = saturation_level
                    instance.previous_background_level = background_level 
                
                raw_image.Release()
                
            except PySpin.SpinnakerException as ex:
                if "timeout" in str(ex).lower():
                    print("Image acquisition timeout")
                else:
                    print(f"Error details: {traceback.format_exc()}")
                    break
                    
    except Exception as ex:
        print(f"Error details: {traceback.format_exc()}")
    finally:
        try:
            cam.EndAcquisition()
        except Exception as ex:
            print(f"Error ending acquisition: {ex}")