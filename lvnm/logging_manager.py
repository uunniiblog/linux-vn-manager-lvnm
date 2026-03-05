import logging
import sys
import config
import os
from logging.handlers import RotatingFileHandler, MemoryHandler

def setup_logging(level=logging.INFO):
    log_level = getattr(logging, level.upper(), logging.INFO)
    log_format = "%(asctime)s - [%(levelname)s] - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    log_path = config.DATA_DIR / "timetracker_test.log"

    # 10 MB cap
    file_handler = RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=1
    )
    file_handler.setFormatter(logging.Formatter(log_format))

    buffered_handler = MemoryHandler(
        capacity=100, 
        flushLevel=logging.ERROR, 
        target=file_handler
    )

    logging.root.handlers = []

    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout), # Sends to terminal
            buffered_handler                   # Sends to file
        ]
    )

    logging.debug(f"Initialized at log level {level}")