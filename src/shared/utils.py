"""Shared logging utilities for AI service modules."""

import datetime
import json
import logging
import os
from typing import Optional

LOG_DIR = "/app/logs"
ERROR_LOG_FILE = os.path.join(LOG_DIR, "aiservice_errors.log")

logger = logging.getLogger(__name__)

try:
    os.makedirs(LOG_DIR, exist_ok=True)
except OSError as e:  # pragma: no cover - catastrophic failure
    logger.error("Cannot create log directory %s: %s", LOG_DIR, e)


def log_error(
    message: str, exception: Optional[Exception] = None, log_file: str = ERROR_LOG_FILE
) -> None:
    """Log an error message and optional exception to a file."""
    timestamp = (
        datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    )
    log_entry = f"{timestamp} - ERROR: {message}"
    if exception:
        log_entry += f" | Exception: {type(exception).__name__}: {exception}"
    logger.error(log_entry)
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception as log_e:  # pragma: no cover - logging failure
        logger.critical(
            "FATAL: Could not write to error log file %s: %s | Original error: %s",
            log_file,
            log_e,
            log_entry,
        )


def log_event(log_file: str, event_type: str, data: dict) -> None:
    """Write a structured event entry to the specified log file."""
    try:
        serializable_data = json.loads(json.dumps(data, default=str))
        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "event_type": event_type,
            **serializable_data,
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:  # pragma: no cover - logging failure
        log_error(f"Failed to write to log file {log_file}", e)
