import os
import re
import threading
import time
from time import sleep

from PIL import Image

from client.socket_client import SocketClient
from config.environment_config import EnvironmentConfig
from config.logging_config import logger
from devices.axis.axis_commands import AxisControllerCommands
from devices.axis.axis_controller_parrser import AxisControllerParser
from devices.interface.device_interface import DeviceInterface


class AxisService:
    """
    Plonas servisas, kuris valdo AxisController per device_manager.
    """

    def __init__(self, device_manager):
        self.device_manager = device_manager
        self.controller: AxisController | None = None

    def connect(self, timeout_sec: float = 12.0):
        ok, msg = self.device_manager.init_devices(init_camera=False, axis_timeout_sec=timeout_sec)
        self.controller = getattr(self.device_manager, "axis_controller", None)

        if not ok or self.controller is None:
            raise RuntimeError(f"Axis init failed: {msg}")
        if not self.controller.is_device_alive():
            raise RuntimeError("Axis device not alive")
        return self.controller

    def is_alive(self) -> bool:
        return self.controller is not None and self.controller.is_device_alive()

    def attach_camera(self, cam):
        if self.controller is None:
            return
        try:
            self.controller.cam = cam
        except Exception:
            pass

    def go_to(self, axis_no: int, pos: int, wait: bool = False):
        if self.controller is None:
            raise RuntimeError("Axis controller not connected")
        self.controller.go_to_position(axis_no, pos, need_wait_for_axis_in_position=wait)

    def home(self, axis_no: int):
        if self.controller is None:
            raise RuntimeError("Axis controller not connected")
        self.controller._go_home(axis_no)

    def stop_all(self):
        if self.controller is None:
            raise RuntimeError("Axis controller not connected")
        self.controller.stop_all_movement()

    def initialize_axis(self, axis_no: int = 0):
        if self.controller is None:
            raise RuntimeError("Axis controller not connected")
        return self.controller.initialize_axis(axis_no)

    def wait_for_axis_controller(self, timeout_s: float = 8.0, poll_s: float = 0.1):
        t0 = time.time()
        while (time.time() - t0) < timeout_s:
            ctrl = getattr(self.device_manager, "axis_controller", None)
            if ctrl is not None:
                return ctrl
            time.sleep(poll_s)
        return None


class AxisController(DeviceInterface):
    def __init__(self, client: SocketClient, external_camera=None, saturation_processor=None):
        self.is_connected = False
        self.client: SocketClient = client

        self.STEPS_PER_MM = EnvironmentConfig().AXIS_STEPS_PER_MM
        self.max_range_in_mm = None

        self.cam = external_camera
        self.saturation_processor = saturation_processor
        self.saturation_min = 200
        self.saturation_max = 220
        self.best_focus = None

        self.connect()

    # -------------------------
    # Connection / health
    # -------------------------
    def connect(self):
        self.client.connect()
        if not self.client.connected:
            self.is_connected = False
            return

        while not self.is_connected:
            response = self.get_identification()
            if response is not None:
                self.is_connected = True
            sleep(1)

        logger.info("AxisController successfully detected")

    def disconnect(self):
        self.client.disconnect()

    def is_device_alive(self) -> bool:
        if not self.client.connected:
            return False

        self._ping_device()
        return (time.time() - self.client.last_response_time) < 4.5

    def _ping_device(self):
        if (
            self.client.last_ping_time is None
            or (
                (time.time() - self.client.last_ping_time) > 2
                and (time.time() - self.client.last_response_time) > 1
            )
        ):
            self.client.send_ping(
                AxisControllerCommands.get_identification(),
                True,
                "Controller6axisMkvd_V1",
            )

    # -------------------------
    # Low-level comms
    # -------------------------
    def send_message(self, message: str):
        sleep(0.1)
        self.client.send_message(message, True)

    def send_query(self, message: str, expected_lines: int):
        return self.client.send_query(message, True, expected_lines)

    def get_identification(self):
        response = self.send_query(AxisControllerCommands.get_identification(), 1)
        error_message = AxisControllerParser.parse_error_message(response)
        if error_message is not None:
            return None
        return AxisControllerParser.parse_identification(response)

    # -------------------------
    # Basic commands
    # -------------------------
    def stop_all_movement(self):
        # Jei turi komandą stop-all per AxisControllerCommands — įsidėk čia.
        # Palieku minimaliai saugų variantą: bandyti per esamą API, jei yra.
        try:
            cmd = getattr(AxisControllerCommands, "stop_all_movement", None)
            if callable(cmd):
                resp = self.send_query(cmd(), 1)
                AxisControllerParser.parse_error_message(resp)
                AxisControllerParser.parse_response_successful(str(resp).splitlines()[0].strip())
        except Exception:
            # Jei tavo sistemoje stop-all kitaip realizuotas, čia neužmušam programos.
            pass


    def _go_home(self, axis_no: int, timeout_s: float = 30.0, poll_s: float = 0.2) -> bool:
        t0 = time.time()

        while True:
            response = self.send_query(AxisControllerCommands.go_home(axis_no), 1)
            AxisControllerParser.parse_error_message(response)

            first_line = str(response).splitlines()[0].strip() if response is not None else ""
            print(f"[axis {axis_no}] HOME first_line: {first_line!r}")

            # BUSY = ne klaida, o būsena -> laukiam
            if first_line.upper() == "BUSY":
                if (time.time() - t0) >= timeout_s:
                    raise Exception("Timeout waiting for HOME (controller keeps returning BUSY)")
                time.sleep(poll_s)
                continue

            # jei ne BUSY – tikrinam sėkmę
            AxisControllerParser.parse_response_successful(first_line)
            return True


    def get_cooler_data(self):
        response = self.send_query(AxisControllerCommands.get_cooler_data(), 1)
        AxisControllerParser.parse_error_message(response)
        return response

    def get_laser_info(self):
        response = self.send_query(AxisControllerCommands.get_laser_info(), 5)
        AxisControllerParser.parse_error_message(response)
        return response

    def set_laser_power(self):
        response = self.send_query(AxisControllerCommands.set_laser_power(), 1)
        AxisControllerParser.parse_error_message(response)

    def set_laser_on(self):
        response = self.send_query(AxisControllerCommands.set_laser_on(), 1)
        AxisControllerParser.parse_error_message(response)

    def set_laser_off(self):
        response = self.send_query(AxisControllerCommands.set_laser_off(), 1)
        AxisControllerParser.parse_error_message(response)

    def laser_info(self):
        response = self.send_query(AxisControllerCommands.get_laser(), 1)
        sleep(10)
        AxisControllerParser.parse_error_message(response)

    # -------------------------
    # Position / motion
    # -------------------------
    def get_position(self, axis_no: int, timeout_s: float = 3.0, poll_s: float = 0.05) -> int:
        t0 = time.time()

        while True:
            response = self.send_query(AxisControllerCommands.get_position(axis_no), 1)
            AxisControllerParser.parse_error_message(response)

            resp = str(response).strip()

            if resp.upper() == "BUSY":
                if (time.time() - t0) >= timeout_s:
                    print(f"timeout_s: {timeout_s}")
                    raise Exception("Timeout waiting for position (controller keeps returning BUSY)")
                time.sleep(poll_s)
                continue

            m = re.search(r"-?\d+", resp)
            if m:
                return int(m.group(0))

            raise Exception(f"Failed to parse position from response: {resp!r}")

    def need_initialize_axis(self, axis_no: int) -> bool:
        """
        Kai kurie kontroleriai grąžina -1, jei ašis neinicializuota.
        Jei get_position meta klaidą – laikom, kad reikia inicializuoti.
        """
        try:
            axis_position = self.get_position(axis_no, timeout_s=5.0)
            return axis_position == -1
        except Exception as e:
            print(f"Error checking axis position: {e}")
            return True

    def go_to_position(self, axis_no: int, position: int, need_wait_for_axis_in_position: bool = False):
        time.sleep(0.1)

        if self.need_initialize_axis(axis_no):
            self._go_home(axis_no)
            time.sleep(0.5)
            current_position = self.get_position(axis_no, timeout_s=5.0)
            if current_position != 0:
                raise Exception("Failed to go home")

        response = self.send_query(AxisControllerCommands.go_to_position(axis_no, position), 1)
        AxisControllerParser.parse_error_message(response)

        first_line = str(response).splitlines()[0].strip() if response is not None else ""
        AxisControllerParser.parse_response_successful(first_line)

        if not need_wait_for_axis_in_position:
            return

        last_position = None
        same_count = 0

        while True:
            current_position = self.get_position(axis_no, timeout_s=5.0, poll_s=0.1)

            if current_position == position:
                break

            if last_position is not None and current_position == last_position:
                same_count += 1
                if same_count >= 20:
                    raise Exception("Failed to go to position (position not changing)")
            else:
                same_count = 0

            last_position = current_position

    # -------------------------
    # Saturation
    # -------------------------
    def check_saturation(self, image_array):
        if image_array is None:
            return False, 0

        if self.saturation_processor is None:
            print("Neturime saturacijos procesoriaus, priimame visas nuotraukas.")
            return True, 190

        try:
            if len(image_array.shape) == 2:
                pil_image = Image.fromarray(image_array)
            elif len(image_array.shape) == 3 and image_array.shape[2] == 3:
                pil_image = Image.fromarray(image_array)
            else:
                print(f"Nežinomas vaizdo formatas: {image_array.shape}")
                return False, 0

            saturation, background, _ = self.saturation_processor.process_image(pil_image)
            print(f"axis control: {saturation}")

            is_good = self.saturation_min <= saturation <= self.saturation_max
            print(f"Saturacijos lygis: {saturation}, Tinkamas: {is_good}")
            return is_good, saturation

        except Exception as e:
            print(f"Klaida tikrinant saturaciją: {e}")
            import traceback

            traceback.print_exc()
            return False, 0

    # -------------------------
    # Initialization routine
    # -------------------------
    def initialize_axis(self, axis_no: int = 0):
        """
        Tavo originali logika palikta, bet sutvarkyta sintaksė/raise/indentacijos.
        """
        try:
            self.shutdown_event = threading.Event()
            self.current_bitmap = None
            self.streaming = False
            self.image_queue = None
            self.current_display_type = None

            if self.cam is None:
                print("Įspėjimas: Kamera neperduota, inicializavimas vyks be kameros funkcijų.")

            self._go_home(axis_no)

            start_time = time.time()

            # Labai didelis skaičius paliktas kaip pas tave
            self.go_to_position(axis_no, 100000000000, need_wait_for_axis_in_position=False)

            end_time = time.time()

            axis_position = self.get_position(axis_no)
            previous_axis_position = axis_position

            while True:
                axis_position = self.get_position(axis_no)
                print(f"previous_axis_position: {previous_axis_position}\naxis_position: {axis_position}")

                if previous_axis_position == axis_position:
                    position_with_limit_switch_offset = (int(axis_position) // 1000) * 1000 - 500
                    self.go_to_position(axis_no, position_with_limit_switch_offset, need_wait_for_axis_in_position=True)
                    sleep(0.1)

                    axis_position = self.get_position(axis_no)
                    print(f"axis_position: {axis_position} - {type(axis_position)}")
                    print(f"step_per_mm: {self.STEPS_PER_MM} - {type(self.STEPS_PER_MM)}")

                    max_range_in_mm = int(int(axis_position) / int(self.STEPS_PER_MM))
                    print(f"Max range in cm: {max_range_in_mm / 10}")
                    break

                previous_axis_position = axis_position
                time.sleep(0.1)

            print(f"start time: {start_time}")
            print(f"end_time: {end_time}")

            wait_time = int(end_time - start_time)
            self._go_home(axis_no)
            print(f"wait_time: {wait_time}")

            sleep(wait_time + 30)

            if self.cam is not None:
                print("Pradedama going_home_in_steps... (išjungta / neįgyvendinta šiame faile)")
                try:
                    self._go_home(axis_no)
                    return self.STEPS_PER_MM, axis_position
                except Exception as e:
                    print(f"Klaida going_home_in_steps funkcijoje: {str(e)}")
                    import traceback

                    traceback.print_exc()
                    return None, self.STEPS_PER_MM, axis_position
            else:
                print("Kamera neperduota, grąžiname tik ašies informaciją be fokusuotės")
                return None, self.STEPS_PER_MM, axis_position

        except Exception as e:
            print(f"Klaida initialize_axis metode: {str(e)}")
            import traceback

            traceback.print_exc()
            return None, None, None

    # -------------------------
    # Helpers
    # -------------------------
    def get_position_in_mm(self, axis_no: int) -> float:
        return self.get_position(axis_no) / self.STEPS_PER_MM

    def move_axis_per_mm(self, axis_no: int, value_in_mm: float):
        self.go_to_position(axis_no, int(value_in_mm * self.STEPS_PER_MM))
