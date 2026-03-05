import logging
import sys
import config
import os
import threading
import traceback
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

    # Log exceptions
    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception

    logging.debug(f"Initialized at log level {level}")

# Log exceptions too
def handle_exception(exc_type, exc_value, exc_traceback):
    """Logs unhandled exceptions."""
    if issubclass(exc_type, KeyboardInterrupt):
        # Allow Ctrl+C to work normally
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.critical("Uncaught exception:", exc_info=(exc_type, exc_value, exc_traceback))

def handle_thread_exception(args):
    """Logs unhandled exceptions in threads."""
    logging.critical(
        f"Uncaught thread exception in {args.thread.name}:", 
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
    )