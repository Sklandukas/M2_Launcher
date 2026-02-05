import traceback
import PySpin
import numpy as np 
import time
import copy

class CameraService:
    def __init__(self, serial_number: str = ""):
        self.serial_number = (serial_number or "").strip()
        self.system = None
        self.cam_list = None
        self.cam = None

    def start(self):
        try:  
            self.system = PySpin.System.GetInstance()
            self.cam_list = self.system.GetCameras()
            num = self.cam_list.GetSize()

            if num == 0:
                self._cleanup()
                return None

            desired_sn = self.serial_number
            selected = None
            first_cam = None

            for i in range(num):
                cam = self.cam_list.GetByIndex(i)
                try:
                    cam.Init()
                except Exception:
                    continue

                if first_cam is None:
                    first_cam = cam

                if not desired_sn:
                    selected = cam
                    break

                try:
                    if PySpin.IsAvailable(cam.DeviceSerialNumber) and PySpin.IsReadable(cam.DeviceSerialNumber):
                        sn = str(cam.DeviceSerialNumber.GetValue()).strip()
                        if sn == desired_sn:
                            selected = cam
                            break
                except Exception:
                    pass

                try:
                    cam.DeInit()
                except Exception:
                    pass

            if selected is None:
                selected = first_cam

            if selected is None:
                self._cleanup()
                return None

            if not selected.IsInitialized():
                selected.Init()

            self.cam = selected

            for i in range(num):
                cam = self.cam_list.GetByIndex(i)
                if cam == self.cam:
                    continue
                try:
                    if cam.IsInitialized():
                        cam.DeInit()
                except Exception:
                    pass

            return self.cam

        except Exception:
            traceback.print_exc()
            self._cleanup()
            return None

    def stop(self):
        self._cleanup()

    def _cleanup(self):
        try:
            if self.cam is not None and self.cam.IsInitialized():
                try:
                    if self.cam.IsStreaming():
                        self.cam.EndAcquisition()
                except Exception:
                    try:
                        self.cam.EndAcquisition()
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            if self.cam is not None and self.cam.IsInitialized():
                self.cam.DeInit()
        except Exception:
            pass

        self.cam = None

        try:
            if self.cam_list is not None:
                self.cam_list.Clear()
        except Exception:
            pass
        self.cam_list = None

        try:
            if self.system is not None:
                self.system.ReleaseInstance()
        except Exception:
            pass
        self.system = None
class SimpleCameraCapture:
    def __init__(self, cam=None):
        self.cam = cam
    
    def set_camera(self, cam):

        self.cam = cam

    def capture_image_at_position(instance, cam, position, previous_sat):
        try:
            acquisition_started = False
            if not cam.IsStreaming():
                cam.BeginAcquisition()
                acquisition_started = True

            timeout_ms = 1500
            try:
                nmap = cam.GetNodeMap()
                exp = PySpin.CFloatPtr(nmap.GetNode('ExposureTime'))
                if PySpin.IsAvailable(exp) and PySpin.IsReadable(exp):
                    exposure_ms = float(exp.GetValue()) / 1000.0
                    timeout_ms = max(2000, int(3 * exposure_ms) + 200)
            except Exception:
                pass

            trig_mode = None
            trig_src_software = False
            tmap = None
            try:
                tmap = cam.GetNodeMap()
                trig = PySpin.CEnumerationPtr(tmap.GetNode('TriggerMode'))
                src  = PySpin.CEnumerationPtr(tmap.GetNode('TriggerSource'))
                if PySpin.IsAvailable(trig) and PySpin.IsReadable(trig):
                    trig_mode = trig.GetCurrentEntry().GetSymbolic()
                if PySpin.IsAvailable(src) and PySpin.IsReadable(src):
                    trig_src = src.GetCurrentEntry().GetSymbolic()
                    trig_src_software = (trig_src == 'Software')
            except Exception:
                tmap = None

            lower = getattr(instance, "saturation_lower_bound", 110.0)
            upper = getattr(instance, "saturation_upper_bound", 205.0)

            best_array = None
            best_penalty = float("inf")  

            attempts = 0
            while attempts < 15:
                attempts += 1

                try:
                    if trig_mode == 'On' and trig_src_software and tmap is not None:
                        ts = PySpin.CCommandPtr(tmap.GetNode('TriggerSoftware'))
                        if PySpin.IsAvailable(ts) and PySpin.IsWritable(ts):
                            ts.Execute()
                except Exception:
                    pass

                try:
                    img = cam.GetNextImage(timeout_ms)
                except PySpin.SpinnakerException:
                    continue

                try:
                    if img.IsIncomplete():
                        continue

                    array = img.GetNDArray().copy()
                    sat = float(np.max(array))

                    if lower <= sat <= upper:
                        return array

                    if sat < lower:
                        penalty = lower - sat
                    elif sat > upper:
                        penalty = sat - upper
                    else:
                        penalty = 0.0

                    if penalty < best_penalty:
                        best_penalty = penalty
                        best_array = array

                finally:
                    try:
                        img.Release()
                    except Exception:
                        pass

            return best_array

        except Exception:
            traceback.print_exc()
            return None
        finally:
            try:
                if 'acquisition_started' in locals() and acquisition_started:
                    cam.EndAcquisition()
            except Exception:
                pass
            
    def capture_multiple(self, count=5, delay_ms=100, timeout_ms=1000):
        if self.cam is None:
            return []
        
        images = []
        is_streaming = self.cam.IsStreaming()
        
        try:
            if not is_streaming:
                self.cam.BeginAcquisition()
            for i in range(count):
                try:
                    image_result = self.cam.GetNextImage(timeout_ms)
                    
                    if image_result.IsIncomplete():
                        image_result.Release()
                        continue
                    
                    image_array = image_result.GetNDArray()
                    images.append(copy.deepcopy(image_array))
                    
                    image_result.Release()
                    
                    if i < count - 1:
                        time.sleep(delay_ms / 1000.0)
                        
                except Exception as e:
                    print(f"Error when capturing an image {i+1}/{count}: {e}")
            
            if not is_streaming:
                self.cam.EndAcquisition()
                
            return images
            
        except Exception as e:
            print(f"{e}")
            
            try:
                if not is_streaming and self.cam.IsStreaming():
                    self.cam.EndAcquisition()
            except:
                pass
                
            return images  
        
    def safe_capture_image(self):
        try:
            if self.cam is None:
                print("Kamera nenustatyta. Negalima fiksuoti nuotraukos.")
                return None

            if hasattr(self.cam, 'IsStreaming'):
                was_streaming = self.cam.IsStreaming()
                
                if not was_streaming:
                    try:
                        print("Pradedame fiksuoti vaizdą...")
                        self.cam.BeginAcquisition()
                    except Exception as e:
                        print(f"Klaida pradedant fiksavimą: {e}")
                        return None

                try:
                    print("Bandome gauti vaizdą...")
                    image_obj = self.cam.GetNextImage(2000)
                    if image_obj.IsIncomplete():
                        print(f"Gautas nepilnas vaizdas. Būsena: {image_obj.GetImageStatus()}")
                        image_array = None
                    else:
                        print("Gauname vaizdą kaip numpy masyvą...")
                        image_array = image_obj.GetNDArray()
                    
                    image_obj.Release()
                    
                    if not was_streaming:
                        self.cam.EndAcquisition()
                        
                    return image_array
                    
                except Exception as e:
                    print(f"Klaida gaunant vaizdą: {e}")
                    if not was_streaming and hasattr(self.cam, 'IsStreaming') and self.cam.IsStreaming():
                        try:
                            self.cam.EndAcquisition()
                        except:
                            pass
                    return None
            elif hasattr(self.cam, 'capture_image'):
                print("Naudojame kameros capture_image metodą...")
                try:
                    image_array = self.cam.capture_image(auto_begin_end=True)
                    return image_array
                except Exception as e:
                    print(f"Klaida naudojant capture_image: {e}")
                    return None
            else:
                print("Nežinomas kameros tipas, negalima fiksuoti vaizdo.")
                return None
                
        except Exception as e:
            print(f"Klaida fiksuojant vaizdą: {e}")
            import traceback
            traceback.print_exc()
            return None