"""Shared logging utilities for AI service modules."""

import datetime
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Dict, Optional

LOG_DIR = "/app/logs"
ERROR_LOG_FILE = os.path.join(LOG_DIR, "aiservice_errors.log")
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3

logger = logging.getLogger(__name__)

try:
    os.makedirs(LOG_DIR, exist_ok=True)
except OSError as e:  # pragma: no cover - catastrophic failure
    logger.error("Cannot create log directory %s: %s", LOG_DIR, e)


_error_logger = logging.getLogger("aiservice.error")
if not _error_logger.handlers:
    handler = RotatingFileHandler(
        ERROR_LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    _error_logger.addHandler(handler)
    _error_logger.setLevel(logging.ERROR)
    _error_logger.propagate = False


_event_loggers: Dict[str, logging.Logger] = {}


def _get_event_logger(log_file: str) -> logging.Logger:
    logger = _event_loggers.get(log_file)
    if logger is None:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        logger = logging.getLogger(f"event.{log_file}")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _event_loggers[log_file] = logger
    return logger


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
    try:
        logger_to_use = (
            _error_logger if log_file == ERROR_LOG_FILE else _get_event_logger(log_file)
        )
        logger_to_use.error(log_entry)
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
        event_logger = _get_event_logger(log_file)
        event_logger.info(json.dumps(log_entry))
    except Exception as e:  # pragma: no cover - logging failure
        log_error(f"Failed to write to log file {log_file}", e)
