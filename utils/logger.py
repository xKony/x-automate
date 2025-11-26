import logging
import os
import sys
from datetime import datetime
from config import SAVE_LOGS, LOG_LEVEL


class CustomFormatter(logging.Formatter):

    grey = "\x1b[38;20m"
    green = "\x1b[32;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format_str = "%(asctime)s | %(levelname)-8s | %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: green + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


def get_logger(module_name):

    # 1. Convert config string to logging level
    # If config is invalid, defaults to logging.INFO
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    level_str = LOG_LEVEL.upper()

    # Safe fallback if config has a typo
    if level_str not in valid_levels:
        level_str = "INFO"

    current_level = getattr(logging, level_str)

    # 2. Create Logger
    logger = logging.getLogger(module_name)
    logger.setLevel(current_level)

    if logger.hasHandlers():
        return logger

    # 3. Create Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(current_level)
    console_handler.setFormatter(CustomFormatter())
    logger.addHandler(console_handler)

    # 4. Create File Handler (if enabled)
    if SAVE_LOGS:
        if not os.path.exists("logs"):
            os.makedirs("logs")

        log_file = datetime.now().strftime("logs/%Y-%m-%d.log")

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(current_level)

        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger
