import socket
import threading
import time
from time import sleep
from config.logging_config import logger

class SocketClient:
    def __init__(self, ip:str, port:int):
        self.ip = ip
        self.port = port
        self.socket = None
        self.connected = False
        self.TIME_DELAY = 0.3
        self.RESPONSE_TIMEOUT = 1
        self.CONNECTION_TIMEOUT = 1
        self.connect()
        self.last_response_time = None
        self.last_ping_time = None
        self.lock = threading.Lock()
        self.freeze_ping = False

    def connect(self):
        if self.socket is not None:
            return
        try:
            logger.info(f"Trying to connect: {self.ip}:{self.port}")
            sleep(5)
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.CONNECTION_TIMEOUT)
            self.socket.connect((self.ip, self.port))
            self.connected = True
            self.socket.settimeout(self.RESPONSE_TIMEOUT)
            logger.info(f"Connected to server: {self.ip}:{self.port}")
            sleep(2)
        except Exception as e:
            self.socket = None
            self.connected = False
            logger.error(f"Connection error: {e}")

    def disconnect(self):
        if self.socket:
            self.socket.close()
            self.socket = None
            self.connected = False
            logger.info("Disconnected from socket server.")

    def is_connected(self):
        if not self.socket:
            return False
        try:
            self.socket.getpeername()
            return True
        except socket.error:
            return False

    def send_message(self, message, new_line=False):
        try:
            sleep(0.1)
            if not self.socket or not self.is_connected():
                return False
            self.clean_input()
            logger.info(f"Sending message: {message}")
            if new_line:
                message += "\n"
            self.socket.sendall(message.encode())
        except Exception as e:
            logger.error("Connection lost. Unable to send the message.")
            self.disconnect()

    def send_query(self, message, new_line=False, expected_response_lines=1, retries=3):
        with self.lock:
            for attempt in range(retries):
                self.freeze_ping = True
                self.send_message(message, new_line)
                response = self._get_message(expected_response_lines)
                if response is not None:
                    self.freeze_ping = False
                    return response
            logger.error(f"Failed to receive query response after {retries} attempts.")
            self.freeze_ping = False
            return None

    def send_ping(self, ping_message, new_line, ping_response_message, retries=3):
        with self.lock:
            for attempt in range(retries):
                if self.freeze_ping:
                    return
                self.send_message(ping_message, new_line)
                response = self._get_message(1)
                if response == ping_response_message:
                    self.last_ping_time = time.time()
                    return
            logger.error(f"Failed to receive ping response after {retries} attempts.")

    def _get_message(self, expected_lines=1, delimiter="\n", retries=3):
            sleep(0.1)
            idle_timeout = 0.2
            if not self.is_connected():
                return
            try:
                self.socket.settimeout(self.RESPONSE_TIMEOUT)
                response_buffer = b""
                last_receive_time = time.time()
                line_count = 0
                while True:
                    chunk = self.socket.recv(1024)
                    if chunk:
                        response_buffer += chunk
                        last_receive_time = time.time()
                        line_count = response_buffer.decode(errors="ignore").count(delimiter)
                    if time.time() - last_receive_time > idle_timeout:
                        break
                    if expected_lines is not None and line_count >= expected_lines:
                        break
                response_buffer = response_buffer.replace(b'\xff', b'')
                response = response_buffer.decode(errors="replace").strip()
                logger.info(f"Received response: {response}")
                if len(response) == 0:
                        logger.warn("Empty response received.")
                        return None
                self.last_response_time = time.time()
                return response
            except socket.timeout:
                    return None
            except Exception as e:
                logger.error(f"Error receiving message: {e}")
                return None

    def clean_input(self):
        if not self.socket or not self.is_connected():
            return
        try:
            self.socket.settimeout(0.2)
            while True:
                try:
                    chunk = self.socket.recv(1024)
                    if not chunk:
                        break
                except socket.timeout:
                    break
        except Exception as e:
            logger.error(f"Error during clean_input: {e}")
        finally:
            self.socket.settimeout(self.RESPONSE_TIMEOUT)

    def __del__(self):
        self.disconnect()
