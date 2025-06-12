import os
import logging
from dotenv import load_dotenv

load_dotenv()

def setup_logger():
    log_level = os.getenv("LOG_LEVEL").upper()
    print(f"Setting log level to: {log_level}")
    numeric_level = getattr(logging, log_level, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    return logging.getLogger()