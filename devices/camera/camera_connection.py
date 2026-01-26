import PySpin
import json
from PIL import Image
import numpy as np
from contextlib import contextmanager

class FlirCameraConnection:
    def __init__(self, config_path):
        self.config = self.load_config(config_path)
        camera_settings = self.config["CameraDefaultSettings"]
        self.width = camera_settings["width"]
        self.height = camera_settings["height"]
        self.exposure_time = camera_settings["exposure_time"]
        self.gain = camera_settings["gain"]
        self.brightness = camera_settings["brightness"]
        self.frame_rate = camera_settings["frame_rate"]
        self.serial_number = camera_settings["serial_number"]
        
        self.connected = False
        self.cam = None
        self.system = None
        self.cam_list = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def load_config(self, filename):
        try:
            with open(filename, "r") as f:
                config = json.load(f)
            return config
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise RuntimeError(f"{e}")

    def _set_parameter(self, node, value, verify=True, description="parametras"):
        try:
            if node.GetAccessMode() == PySpin.RW:
                node.SetValue(value, verify)
                return True
            else:
                print(f"{description}")
                return False
        except PySpin.SpinnakerException as ex:
            print(f"{description}: {ex}")
            return False

    def set_default_configuration(self, cam):
        try:
            self._set_parameter(cam.ExposureAuto, PySpin.ExposureAuto_Off, 
                               description="ExposureAuto")
            self._set_parameter(cam.GainAuto, PySpin.GainAuto_Off, 
                               description="GainAuto")
            
            self._set_parameter(cam.ExposureTime, self.exposure_time, 
                               description="ExposureTime")
            self._set_parameter(cam.Width, int(self.width), False, 
                               description="Width")
            self._set_parameter(cam.Height, int(self.height), False, 
                               description="Height")
            self._set_parameter(cam.Gain, self.gain, 
                               description="Gain")
            self._set_parameter(cam.PixelFormat, PySpin.PixelFormat_Mono8, 
                               description="PixelFormat")
            
            if hasattr(cam, "SharpnessAuto"):
                self._set_parameter(cam.SharpnessAuto, PySpin.SharpnessAuto_Off, 
                                  description="SharpnessAuto")
            self._set_parameter(cam.BlackLevel, self.brightness, 
                               description="BlackLevel")
            self._set_parameter(cam.Gamma, 0.5, False, 
                               description="Gamma")
            
            try:
                if hasattr(cam, "AcquisitionFrameRateEnable") and \
                   cam.AcquisitionFrameRateEnable.GetAccessMode() == PySpin.RW:
                    cam.AcquisitionFrameRateEnable.SetValue(True)
                    if hasattr(cam, "AcquisitionFrameRate") and \
                       cam.AcquisitionFrameRate.GetAccessMode() == PySpin.RW:
                        cam.AcquisitionFrameRate.SetValue(self.frame_rate)
            except PySpin.SpinnakerException as ex:
                print(f"{ex}")
                
            return True
            
        except PySpin.SpinnakerException as ex:
            return False

    def connect(self):
        if self.connected:
            return self.cam, self.system, self.cam_list
            
        try:
            self.system = PySpin.System.GetInstance()
            self.cam_list = self.system.GetCameras()

            if self.cam_list.GetSize() == 0:
                self.cam_list.Clear()
                self.system.ReleaseInstance()
                self.system = None
                self.cam_list = None
                return None, None, None
            
            for i in range(self.cam_list.GetSize()):
                camera = self.cam_list.GetByIndex(i)
                try:
                    camera.Init()
                    serial_number = camera.DeviceSerialNumber.GetValue()
                    if serial_number == self.serial_number:
                        self.cam = camera
                        break  
                    camera.DeInit() 
                except PySpin.SpinnakerException as ex:
                    camera.DeInit()

            if self.cam is None:
                self.cam_list.Clear()
                self.system.ReleaseInstance()
                self.system = None
                self.cam_list = None
                return None, None, None

            if not self.cam.IsInitialized():
                self.cam.Init()

            if self.set_default_configuration(self.cam):
                self.connected = True
            
            return self.cam, self.system, self.cam_list
            
        except PySpin.SpinnakerException as ex:
            self.disconnect()
            return None, None, None
    
    def disconnect(self):
        try:
            if self.cam is not None:
                if self.cam.IsStreaming():
                    self.cam.EndAcquisition()
                
                if self.cam.IsInitialized():
                    self.cam.DeInit()
                self.cam = None
                
            if self.cam_list is not None:
                self.cam_list.Clear()
                self.cam_list = None
                
            if self.system is not None:
                self.system.ReleaseInstance()
                self.system = None
                
            self.connected = False

        except PySpin.SpinnakerException as ex:
            print(f"Klaida atjungiant kamerą: {ex}")
    
    def capture_image(self, save_path=None, auto_begin_end=True):
        if not self.connected or self.cam is None:
            return None
            
        try:
            was_streaming = self.cam.IsStreaming()
            if not was_streaming and auto_begin_end:
                self.cam.BeginAcquisition()
            image = self.cam.GetNextImage(2000)  
            
            if image.IsIncomplete():
                image.Release()
                
                if not was_streaming and auto_begin_end and self.cam.IsStreaming():
                    self.cam.EndAcquisition()
                    
                return None
                
            try:
                pixel_format_enum = image.GetPixelFormat()
                
            
                if hasattr(PySpin, 'GetPixelFormatName'):
                    format_name = PySpin.GetPixelFormatName(pixel_format_enum)
                else:
                    print(f"Vaizdo formatas ID: {pixel_format_enum}")
                 
                if pixel_format_enum == PySpin.PixelFormat_Mono8:
                    img_data = image.GetNDArray()
                    print("Aptiktas Mono8 formatas")
                elif pixel_format_enum == PySpin.PixelFormat_Mono8:
                    img_data = image.GetNDArray()
                    img_data = (img_data / 256).astype(np.uint8) 
                elif pixel_format_enum in [PySpin.PixelFormat_RGB8, PySpin.PixelFormat_BGR8]:
                    img_data = image.GetNDArray()
                else:
                    try:
                        converted_image = image.Convert(PySpin.PixelFormat_Mono8)
                        img_data = converted_image.GetNDArray()
                    except Exception as ex:
                        img_data = image.GetNDArray()
            except Exception as e:
                img_data = image.GetNDArray()
            image.Release()
            if not was_streaming and auto_begin_end and self.cam.IsStreaming():
                self.cam.EndAcquisition()
            
            if img_data is None or img_data.size == 0:
                return None
                
            if save_path:
                pil_image = Image.fromarray(img_data)
                pil_image.save(save_path)
            return img_data
            
        except PySpin.SpinnakerException as ex:
            if auto_begin_end and self.cam and self.cam.IsStreaming() and not was_streaming:
                try:
                    self.cam.EndAcquisition()
                except:
                    pass
                    
            return None
    
    def set_exposure(self, exposure_time):
        if not self.connected or self.cam is None:
            return False
            
        try:
            if self.cam.ExposureAuto.GetAccessMode() == PySpin.RW:
                self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
            
            if self.cam.ExposureTime.GetAccessMode() == PySpin.RW:
                self.cam.ExposureTime.SetValue(exposure_time)
                self.exposure_time = exposure_time
                return True
            else:
                return False
        except PySpin.SpinnakerException as ex:
            return False
    
    def set_gain(self, gain):
        if not self.connected or self.cam is None:
            return False
            
        try:
            if self.cam.GainAuto.GetAccessMode() == PySpin.RW:
                self.cam.GainAuto.SetValue(PySpin.GainAuto_Off)
            
            if self.cam.Gain.GetAccessMode() == PySpin.RW:
                self.cam.Gain.SetValue(gain)
                self.gain = gain
                return True
            else:
                return False
        except PySpin.SpinnakerException as ex:
            return False
    
    @contextmanager
    def streaming_context(self):
        if not self.connected or self.cam is None:
            yield None
            return
            
        try:
            self.cam.BeginAcquisition()
            yield self.cam
        finally:
            if self.cam and self.cam.IsStreaming():
                self.cam.EndAcquisition()