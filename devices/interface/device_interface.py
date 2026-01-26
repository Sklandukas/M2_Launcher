from abc import ABC, abstractmethod

class DeviceInterface(ABC):
    @abstractmethod
    def __init__(self, client: object) -> None:
        pass

    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def is_device_alive(self) -> bool:
        pass

    @abstractmethod
    def send_message(self, message: str) -> None:
        pass

    @abstractmethod
    def send_query(self, message, expected_lines)-> str:
        pass

    @abstractmethod
    def get_identification(self) -> str:
        pass
