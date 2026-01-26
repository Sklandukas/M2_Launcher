from config.logging_config import logger

class AxisControllerParser:
    @staticmethod
    def parse_identification(response):
        if response is not None and response == "Controller6axisMkvd_V1":
            return response
        return None

    @staticmethod
    def parse_get_position(response):
        try:
            position = int(response)
            return position
        except Exception as e:
            logger.error(e)
            raise Exception("Failed to parse position.")

    @staticmethod
    def parse_response_successful(response):
        if response is not None and response == "OK":
            return response
        raise Exception("Command was not successful.")

    @staticmethod
    def parse_error_message(response):
        if response is not None and "Error_1" in response:
            logger.warn("Unknown command.")
        if response is not None and "Error_2" in response:
            logger.warn("Axis does not exist.")
        if response is not None and "Error_" in response:
            logger.warn("Unknown error")


