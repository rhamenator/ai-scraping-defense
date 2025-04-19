# shared/honeypot_logger.py
# Dedicated logger for honeypot trigger events.

import logging
import json
import datetime
import os

# --- Configuration ---
HONEYPOT_LOG_FILE = "/app/logs/honeypot_hits.log" # Ensure /app/logs is mounted volume
os.makedirs(os.path.dirname(HONEYPOT_LOG_FILE), exist_ok=True) # Create log dir if needed

# --- Logger Setup ---

# Create a specific logger instance
honeypot_logger = logging.getLogger('honeypot_logger')
honeypot_logger.setLevel(logging.INFO)
honeypot_logger.propagate = False # Prevent duplicating logs to root logger

# Create a JSON formatter
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            'timestamp': datetime.datetime.utcfromtimestamp(record.created).isoformat() + 'Z',
            'level': record.levelname,
            'message': record.getMessage(),
            # Add extra context passed to the logger
            **(record.details if hasattr(record, 'details') else {})
        }
        return json.dumps(log_record)

# Configure file handler only if not already configured (prevents duplicates on reload)
if not honeypot_logger.hasHandlers():
    try:
        file_handler = logging.FileHandler(HONEYPOT_LOG_FILE)
        formatter = JsonFormatter()
        file_handler.setFormatter(formatter)
        honeypot_logger.addHandler(file_handler)
        print(f"Honeypot logger configured to write to {HONEYPOT_LOG_FILE}")
    except Exception as e:
        print(f"ERROR setting up honeypot file logger: {e}")
        # Optionally add a StreamHandler as fallback for visibility
        # stream_handler = logging.StreamHandler()
        # stream_handler.setFormatter(formatter)
        # honeypot_logger.addHandler(stream_handler)

# --- Logging Function ---

def log_honeypot_hit(details: dict):
    """
    Logs a honeypot hit event with structured details.

    Args:
        details (dict): A dictionary containing information about the hit,
                        e.g., {'ip': '...', 'user_agent': '...', 'path': '...', ...}
    """
    try:
        # Use the 'extra' argument mechanism for structured logging
        honeypot_logger.info("Honeypot triggered", extra={'details': details})
    except Exception as e:
        # Log error to stderr if logger fails
        print(f"ERROR in log_honeypot_hit: {e}. Details: {details}")

# Example usage (for testing this module directly)
# if __name__ == "__main__":
#     test_details = {
#         "ip": "1.2.3.4",
#         "user_agent": "Test Honeypot Client",
#         "method": "GET",
#         "path": "/tarpit/decoy-link-xyz",
#         "referer": "-",
#         "status": 200
#     }
#     log_honeypot_hit(test_details)
#     print(f"Check {HONEYPOT_LOG_FILE} for the log entry.")