import logging
import sys
import config
import os
import threading
import traceback
import atexit
from settings_manager import SettingsManager

def setup_logging(level=logging.INFO):
    log_level = getattr(logging, level.upper(), logging.INFO)
    log_format = "%(asctime)s - [%(levelname)s] - %(module)s:%(lineno)d - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logging.root.handlers = []
    handlers = [logging.StreamHandler(sys.stdout)]

    user_settings = SettingsManager()
    write_to_file = user_settings.get(config.USER_CONF_LOG_TO_FILE, False)

    if write_to_file:
        log_path = config.DATA_DIR / "timetracker_test.log"
        file_handler = logging.FileHandler(
            log_path, mode='w', encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)


    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=handlers
    )

    # Log exceptions
    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception

    # Automatically flush and save all memory buffers when sys.exit() or normal exit occurs
    atexit.register(logging.shutdown)

    logging.debug(f"Initialized at log level {level}")

# Log exceptions too
def handle_exception(exc_type, exc_value, exc_traceback):
    """Logs unhandled exceptions."""
    if issubclass(exc_type, KeyboardInterrupt):
        # Allow Ctrl+C to work normally
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.critical("Uncaught exception:", exc_info=(exc_type, exc_value, exc_traceback))

    # Force an immediate disk write before the app crashes out completely
    logging.shutdown()

def handle_thread_exception(args):
    """Logs unhandled exceptions in threads."""
    logging.critical(
        f"Uncaught thread exception in {args.thread.name}:", 
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
    )
    # logging.shutdown()