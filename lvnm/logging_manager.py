import logging
import sys

def setup_logging(level=logging.INFO):
    log_level = getattr(logging, level.upper(), logging.INFO)
    log_format = "%(asctime)s - [%(levelname)s] - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Reset any existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout) # Sends to terminal
            # logging.FileHandler("app.log")   # Optional: Sends to a file
        ]
    )

    logging.info(f"Initialized at log level {level}")