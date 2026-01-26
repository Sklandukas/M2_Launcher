import PySpin
import traceback

def update_camera_settings(instance, cam, saturation_level, background_level):
    try:
        new_shutter = calculate_shutter(instance, saturation_level, background_level)

        if PySpin.IsAvailable(cam.ExposureTime) and PySpin.IsWritable(cam.ExposureTime):
            cam.ExposureTime.SetValue(new_shutter)
            instance.last_known_exposure_time = new_shutter
        else:
            print("ExposureTime is not available or writable")

    except PySpin.SpinnakerException as ex:
        print(f"Error updating camera settings: {ex}")
        print(f"Error details: {traceback.format_exc()}")
    except Exception as ex:
        print(f"Unexpected error in update_camera_settings: {ex}")
        print(f"Error details: {traceback.format_exc()}")


def set_default_configuration(instance, cam):
    try:
        node_map = cam.GetNodeMap()
        features = PySpin.CCategoryPtr(node_map.GetNode("Root")).GetFeatures()
        for feature in features:
            feature_name = PySpin.CValuePtr(feature).ToString()
            print(f"  - {feature_name}")
        
        print(f"Setting Width to {int(instance.camera_settings.get('width', 1288))}")
        if PySpin.IsAvailable(cam.Width) and PySpin.IsWritable(cam.Width):
            cam.Width.SetValue(int(instance.camera_settings.get("width", 1288)))
            print(f"Width set to {cam.Width.GetValue()}")
        else:
            print("Width is not available or writable")
            
        print(f"Setting Height to {int(instance.camera_settings.get('height', 964))}")
        if PySpin.IsAvailable(cam.Height) and PySpin.IsWritable(cam.Height):
            cam.Height.SetValue(int(instance.camera_settings.get("height", 964)))
            print(f"Height set to {cam.Height.GetValue()}")
        else:
            print("Height is not available or writable")
        
        if PySpin.IsAvailable(cam.ExposureTime) and PySpin.IsWritable(cam.ExposureTime):
            cam.ExposureTime.SetValue(instance.last_known_exposure_time)
            print(f"ExposureTime set to {cam.ExposureTime.GetValue()}")
        else:
            print("ExposureTime is not available or writable")
        
        print(f"Setting Gain to {instance.camera_settings.get('gain', 0)}")
        if PySpin.IsAvailable(cam.Gain) and PySpin.IsWritable(cam.Gain):
            cam.Gain.SetValue(instance.camera_settings.get("gain", 0))
            print(f"Gain set to {cam.Gain.GetValue()}")
        else:
            print("Gain is not available or writable")
        
        if PySpin.IsAvailable(cam.PixelFormat) and PySpin.IsWritable(cam.PixelFormat):
            cam.PixelFormat.SetValue(PySpin.PixelFormat_Mono8)
            print(f"PixelFormat set to {cam.PixelFormat.GetCurrentEntry().GetSymbolic()}")
        else:
            print("PixelFormat is not available or writable")
        
        print("Setting ExposureAuto to Off")
        if PySpin.IsAvailable(cam.ExposureAuto) and PySpin.IsWritable(cam.ExposureAuto):
            cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
            print(f"ExposureAuto set to {cam.ExposureAuto.GetCurrentEntry().GetSymbolic()}")
        else:
            print("ExposureAuto is not available or writable")
        
        if PySpin.IsAvailable(cam.GainAuto) and PySpin.IsWritable(cam.GainAuto):
            cam.GainAuto.SetValue(PySpin.GainAuto_Off)
            print(f"GainAuto set to {cam.GainAuto.GetCurrentEntry().GetSymbolic()}")
        else:
            print("GainAuto is not available or writable")
        
        print(f"Setting BlackLevel to {instance.camera_settings.get('brightness', 2)}")
        if PySpin.IsAvailable(cam.BlackLevel) and PySpin.IsWritable(cam.BlackLevel):
            cam.BlackLevel.SetValue(instance.camera_settings.get("brightness", 2))
        else:
            print("BlackLevel is not available or writable")
        
        if PySpin.IsAvailable(cam.AcquisitionFrameRateEnable) and PySpin.IsWritable(cam.AcquisitionFrameRateEnable):
            cam.AcquisitionFrameRateEnable.SetValue(True)
            print(f"AcquisitionFrameRateEnable set to {cam.AcquisitionFrameRateEnable.GetValue()}")
        else:
            print("AcquisitionFrameRateEnable is not available or writable")
            
        print(f"Setting AcquisitionFrameRate to {instance.camera_settings.get('frame_rate', 30)}")
        if PySpin.IsAvailable(cam.AcquisitionFrameRate) and PySpin.IsWritable(cam.AcquisitionFrameRate):
            cam.AcquisitionFrameRate.SetValue(instance.camera_settings.get("frame_rate", 30))
            print(f"AcquisitionFrameRate set to {cam.AcquisitionFrameRate.GetValue()}")
        else:
            print("AcquisitionFrameRate is not available or writable")
            
    except PySpin.SpinnakerException as ex:
        print(f"Error in setting camera parameters: {ex}")
        print(f"Error details: {traceback.format_exc()}")       

def calculate_shutter(instance, saturation_level, background_level):
    min_shutter = 51
    max_shutter = 1036380
    target_saturation = 200  # Tikslinis saturacijos lygis

    saturation_level = saturation_level

    shutter = float(getattr(instance, "last_known_exposure_time", 1000))
    
    # Gauti ankstesnę saturaciją stabilumui
    prev_saturation = getattr(instance, "prev_saturation", saturation_level)
    
    dead_lo, dead_hi = 190, 210
    
    # Adaptyvūs žingsniai pagal atstumą nuo tikslo
    distance_from_target = abs(saturation_level - target_saturation)
    
    if distance_from_target > 70:
        step_big = 0.15    # 15% kai labai toli
        step_small = 0.08  # 8% kai toli
    elif distance_from_target > 50:
        step_big = 0.10    # 10% kai vidutiniškai toli
        step_small = 0.05  # 5% kai arti
    else:
        step_big = 0.07    # 7% kai arti
        step_small = 0.03  # 3% kai labai arti

    # 1) Deadband
    if dead_lo <= saturation_level <= dead_hi:
        new_shutter = shutter
        instance.status = "Optimal Saturation"

    # 2) Per didelė saturacija
    elif saturation_level > dead_hi:
        # Tikslus koregavimas pagal saturacijos lygį
        if saturation_level > 300:
            # Labai didelis koregavimas
            target_factor = target_saturation / saturation_level
            factor = max(0.7, min(0.95, target_factor))  # Ribojame ekstremalias vertes
        elif saturation_level > 150:
            factor = 1.0 - step_big   # -10-15 %
        else:
            factor = 1.0 - step_small # -3-8 %
            
        new_shutter = shutter * factor
        instance.status = f"Decreasing (High Saturation {saturation_level})"

    # 3) Per maža saturacija
    elif saturation_level < dead_lo:
        # Tikslus koregavimas pagal saturacijos lygį
        if saturation_level < 50:
            # Labai didelis koregavimas
            target_factor = target_saturation / saturation_level
            factor = min(1.5, max(1.05, target_factor))  # Ribojame ekstremalias vertes
        elif saturation_level < 150:
            factor = 1.0 + step_big   # +10-15 %
        else:
            factor = 1.0 + step_small # +3-8 %
            
        new_shutter = shutter * factor
        instance.status = f"Increasing (Low Saturation {saturation_level})"

    # 4) Svyravimo prevencija - jei keitėsi kryptis
    if hasattr(instance, 'adjustment_history'):
        if len(instance.adjustment_history) >= 2:
            # Tikriname ar vyksta svyravimas
            last_two = instance.adjustment_history[-2:]
            if (last_two[0] > 1.0 and last_two[1] < 1.0) or (last_two[0] < 1.0 and last_two[1] > 1.0):
                # Sumažiname koregavimą jei vyksta svyravimas
                if 'factor' in locals():
                    if factor > 1.0:
                        factor = 1.0 + (factor - 1.0) * 0.5  
                    else:
                        factor = 1.0 - (1.0 - factor) * 0.5  
                    instance.status += " (Oscillation Dampening)"
    if not hasattr(instance, 'adjustment_history'):
        instance.adjustment_history = []
    if 'factor' in locals():
        instance.adjustment_history.append(factor)
        
        if len(instance.adjustment_history) > 5:
            instance.adjustment_history = instance.adjustment_history[-5:]

    if background_level > 30:
        corr = max(0.95, 1 - 0.002 * (background_level - 30))  
        if 'new_shutter' in locals():
            new_shutter *= corr
            instance.status += f" + Background Correction ({background_level})"
        else:
            new_shutter = shutter * corr
            instance.status = f"Background Correction ({background_level})"
    if 'new_shutter' not in locals():
        new_shutter = shutter
    new_shutter = max(min_shutter, min(new_shutter, max_shutter))
    instance.prev_saturation = saturation_level

    return int(new_shutter)

def calculate_shutter_pid(instance, saturation_level, background_level):
    min_shutter = 51
    max_shutter = 1_100_000
    target_saturation = 200

    shutter = float(getattr(instance, "last_known_exposure_time", 1000))
    
    Kp = 0.01  
    Ki = 0.001 
    Kd = 0.005 
    
    dead_lo, dead_hi = 190, 200
    if dead_lo <= saturation_level <= dead_hi:
        instance.status = "Optimal Saturation"
        return int(shutter)
    
    error = target_saturation - saturation_level
    
    if not hasattr(instance, 'pid_integral'):
        instance.pid_integral = 0
        instance.pid_prev_error = 0
    
    instance.pid_integral += error
    derivative = error - instance.pid_prev_error
    
    instance.pid_integral = max(-1000, min(instance.pid_integral, 1000))

    pid_output = Kp * error + Ki * instance.pid_integral + Kd * derivative

    factor = 1.0 + pid_output
    factor = max(0.5, min(factor, 2.0))    
    new_shutter = shutter * factor
    
    if background_level > 30:
        corr = max(0.95, 1 - 0.002 * (background_level - 30))
        new_shutter *= corr
        instance.status = f"PID Control (error: {error:.1f}) + Background Correction"
    else:
        instance.status = f"PID Control (error: {error:.1f})"
    instance.pid_prev_error = error
    new_shutter = max(min_shutter, min(new_shutter, max_shutter))
    
    return int(new_shutter)