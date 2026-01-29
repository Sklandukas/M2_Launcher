import threading
import time
import traceback
from time import sleep
from typing import Type
from ping3 import ping
from client.socket_client import SocketClient
from config.environment_config import EnvironmentConfig
from config.logging_config import logger
from devices.axis.axis_service import AxisController
from devices.global_devices import GlobalDevices

AXIS_CONTROLLER_IP = EnvironmentConfig().AXIS_CONTROLLER_IP
AXIS_CONTROLLER_PORT = EnvironmentConfig().AXIS_CONTROLLER_PORT
SOCKET_DEVICE_CONFIGS = [{"name": "Axis Controller", "ip": AXIS_CONTROLLER_IP,"port":AXIS_CONTROLLER_PORT,"class": AxisController, "attr": "axis_controller"},]

class DevicesRunner:
    def __init__(self):
        self.keep_alive_runner = True
        self.lock = threading.Lock()
        self.device_check_interval = 10
        self._device_threads = {}
        self._last_main_thread_check = None
        self.main_thread_check_interval = 2

    def run(self):
        self._initialize_devices_in_threads()
        while self.keep_alive_runner:
            if not self._is_main_thread_alive():
                self._stop()
            time.sleep(0.1)

    def _initialize_devices_in_threads(self):
        logger.info("Initializing devices in threads...")
        for config in SOCKET_DEVICE_CONFIGS:
            self._device_threads[config["attr"]] = threading.Thread(
                target=self._initialize_socket_device,
                args=(config["name"], config["ip"],config["port"], config["class"], config["attr"]),
                daemon=True)
        for thread in self._device_threads.values():
            thread.start()


    def _initialize_socket_device(self, device_name: str, device_ip: str, device_port:int, device_class: Type, global_device_attr: str):
        last_device_check = None
        last_connecting = None
        reconnect_interval = 5
        check_interval = 0.5
        global_devices = GlobalDevices()
        device_lock_attr = f"{global_device_attr}_lock"
        device_lock = getattr(global_devices, device_lock_attr)

        while self.keep_alive_runner:
            try:
                current_time = time.time()
                device_instance = getattr(global_devices, global_device_attr)
                if device_instance is None:
                    if self._should_execute(last_connecting, reconnect_interval):
                        logger.info(f"Creating/reconnecting {device_name}")
                        last_connecting = time.time()
                        with device_lock:
                            device_instance = device_class(SocketClient(device_ip, device_port))
                            setattr(global_devices, global_device_attr, device_instance)
                else:
                    if self._should_execute(last_device_check, check_interval):
                        if not self._is_device_alive(device_instance):
                            logger.info(f"{device_name} not alive, resetting adapter")
                            with device_lock:
                                device_instance.disconnect()
                                setattr(global_devices, global_device_attr, None)
                            last_device_check = current_time
            except Exception as e:
                logger.error(f"Exception in {device_name} initialization: {e}")
                traceback.print_exc()
                device_instance = getattr(global_devices, global_device_attr)
                if device_instance is not None:
                    with device_lock:
                        device_instance.disconnect()
                        setattr(global_devices, global_device_attr, None)
            sleep(0.1)

        device_instance = getattr(global_devices, global_device_attr)
        if device_instance is not None:
            with device_lock:
                device_instance.disconnect()
                setattr(global_devices, global_device_attr, None)


    def _should_execute(self, last_check, interval):
        current_time = time.time()
        if last_check is None or current_time - last_check >= interval:
            return current_time
        return None

    def _is_main_thread_alive(self):
        current_time = time.time()
        is_time_to_check_main_thread_alive = False
        if self._last_main_thread_check is None:
            self._last_main_thread_check = current_time
            is_time_to_check_main_thread_alive = True
        if current_time - self._last_main_thread_check >= self.main_thread_check_interval:
            self._last_main_thread_check = current_time
            is_time_to_check_main_thread_alive = True
        if is_time_to_check_main_thread_alive:
            return threading.main_thread().is_alive()
        return True

    def _is_device_alive(self, device):
        return device is not None and device.is_device_alive()

    def _stop(self):
        logger.info("Stopping devices runner...")
        self.keep_alive_runner = False

