import threading
from typing import Optional
from devices.axis.axis_service import AxisService

class GlobalDevices:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(GlobalDevices, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self.axis_controller: Optional[AxisService] = None
            self.axis_controller_lock = threading.Lock()
            self._initialized = True

    def get_axis_controller(self) -> Optional[AxisService]:
        return self.axis_controller

