import os
import sys
from dotenv import load_dotenv, find_dotenv
from config.logging_config import logger

class EnvironmentConfig:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_env_vars()
        return cls._instance

    def _load_env_vars(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
            dotenv_path = os.path.join(base_path, ".env")
        else:
            dotenv_path = find_dotenv()

        logger.info(f"Looking for .env at: {dotenv_path}")

        if not os.path.exists(dotenv_path):
            logger.error(".env file not found! Please ensure it exists.")
            exit(1)

        load_dotenv(dotenv_path)

        try:
            self.AXIS_CONTROLLER_IP = os.getenv("AXIS_CONTROLLER_IP", None)
            self.AXIS_CONTROLLER_PORT = int(os.getenv("AXIS_CONTROLLER_PORT", None))
            self.AXIS_STEPS_PER_MM = int(os.getenv("AXIS_STEPS_PER_MM", None))
        except Exception as e:
            logger.error(f"Error loading environment variables: {e}")
            exit(1)

    def validate_environment(self):
        required_vars = {
            "AXIS_CONTROLLER_IP": self.AXIS_CONTROLLER_IP,
            "AXIS_CONTROLLER_PORT": self.AXIS_CONTROLLER_PORT,
            "AXIS_STEPS_PER_MM": self.AXIS_STEPS_PER_MM,
        }

        missing_vars = [key for key, value in required_vars.items() if value is None]

        if missing_vars:
            for var in missing_vars:
                logger.warning(f"⚠️ {var} is not set in the environment variables!")
            exit(1)
        else:
            logger.info("✅ All required environment variables are set.")
