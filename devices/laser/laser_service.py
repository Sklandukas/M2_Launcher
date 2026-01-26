import re

class LaserService:
    def __init__(self, axis_controller):
        self.ctrl = axis_controller
        self.laser_on = False

    @staticmethod
    def parse_wavelength(item_code: str) -> float:
        try:
            wavelength = item_code.split("-")[0].replace("L", "")
            return float(wavelength)
        except Exception as e:
            raise ValueError("Error parsing laser wavelength") from e

    @staticmethod
    def parse_info(info: str):
        serial = None
        model = None

        if info:
            s_n = re.search(r"S/N:\s*([^\s]+)", info)
            if s_n:
                serial = s_n.group(1)

            model_raw = re.search(r"model:\s*([^\s]+)", info, re.IGNORECASE)
            if model_raw:
                model = model_raw.group(1)

        return serial, model

    def turn_on(self):
        if self.laser_on:
            return

        self.ctrl.set_laser_power()
        self.ctrl.set_laser_on()
        self.laser_on = True

    def turn_off(self):
        if not self.laser_on:
            return
        self.ctrl.set_laser_off()
        self.laser_on = False

    def get_laser_info(self):
        try:
            info = self.ctrl.get_laser_info()
        except Exception:
            info = None
        serial, model = self.parse_info(info or "")
        wavelength = None
        if model:
            try:
                wavelength = self.parse_wavelength(model)
            except Exception:
                wavelength = None
        return info, serial, model, wavelength
