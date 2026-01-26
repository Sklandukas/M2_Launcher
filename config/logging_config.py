import logging
import sys
import colorlog
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "app.log"

color_formatter = colorlog.ColoredFormatter(
    "%(log_color)s%(asctime)s - %(levelname)s - [%(threadName)s (%(funcName)s)] [%(filename)s:%(lineno)d] - %(message)s",
    log_colors={
        "DEBUG": "white",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold_red",
    },
)

file_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - [%(threadName)s (%(funcName)s)] [%(filename)s:%(lineno)d] - %(message)s"
)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(color_formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)


