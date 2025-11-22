# shared/honeypot_logger.py
# Dedicated logger for honeypot trigger events.
"""Logging utilities for honeypot hits."""

import datetime
import json
import logging
import os

# --- Configuration ---
HONEYPOT_LOG_FILE = globals().get(
    "HONEYPOT_LOG_FILE",
    os.getenv("HONEYPOT_LOG_FILE", "/app/logs/honeypot_hits.log"),
)
_honeypot_log_available = False
try:
    os.makedirs(os.path.dirname(HONEYPOT_LOG_FILE), exist_ok=True)
    _honeypot_log_available = True
except OSError as e:
    # In test or development environments, /app may not exist or be writable
    # Fall back to a temp directory
    import tempfile
    print(f"WARNING: Cannot create honeypot log directory {HONEYPOT_LOG_FILE}: {e}. Using temp directory.")
    HONEYPOT_LOG_FILE = os.path.join(tempfile.gettempdir(), "honeypot_hits.log")
    try:
        os.makedirs(os.path.dirname(HONEYPOT_LOG_FILE), exist_ok=True)
        _honeypot_log_available = True
    except OSError:
        print(f"WARNING: Cannot create honeypot log directory in temp, file logging disabled")
        _honeypot_log_available = False

# --- Logger Setup ---

# Create a specific logger instance
honeypot_logger = logging.getLogger("honeypot_logger")
honeypot_logger.setLevel(logging.INFO)
honeypot_logger.propagate = False  # Prevent duplicating logs to root logger
# Ensure attribute exists for tests that patch logging.getLogger
if not hasattr(honeypot_logger, "handlers"):
    honeypot_logger.handlers = []


# Create a JSON formatter
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.datetime.fromtimestamp(
                record.created, datetime.timezone.utc
            )
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "message": record.getMessage(),
            # Add extra context passed to the logger
            **getattr(record, "details", {}),
        }
        return json.dumps(log_record)


# Configure file handler only if not already configured (prevents duplicates on reload)
if not honeypot_logger.hasHandlers():
    if _honeypot_log_available:
        try:
            file_handler = logging.FileHandler(HONEYPOT_LOG_FILE)
            formatter = JsonFormatter()
            file_handler.setFormatter(formatter)
            honeypot_logger.addHandler(file_handler)
            print(f"Honeypot logger configured to write to {HONEYPOT_LOG_FILE}")
        except OSError as e:
            print(f"WARNING: Cannot set up honeypot file logger: {e}. Using console only.")
            # Fall back to console logging
            console_handler = logging.StreamHandler()
            formatter = JsonFormatter()
            console_handler.setFormatter(formatter)
            honeypot_logger.addHandler(console_handler)
    else:
        # No file logging available, use console only
        console_handler = logging.StreamHandler()
        formatter = JsonFormatter()
        console_handler.setFormatter(formatter)
        honeypot_logger.addHandler(console_handler)

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
        honeypot_logger.info("Honeypot triggered", extra={"details": details})
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
