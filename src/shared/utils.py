import datetime
import json
import logging
import os
import random
import time
from logging.handlers import RotatingFileHandler
from typing import Dict, Optional

LOG_DIR = os.getenv("LOG_DIR", "/app/logs")
ERROR_LOG_FILE = os.path.join(LOG_DIR, "aiservice_errors.log")
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3

logger = logging.getLogger(__name__)

_log_dir_available = False
try:
    os.makedirs(LOG_DIR, exist_ok=True)
    _log_dir_available = True
except OSError as e:  # pragma: no cover - catastrophic failure
    # In test or development environments, /app may not exist or be writable
    # Fall back to a temp directory
    import tempfile

    logger.warning(
        "Cannot create log directory %s: %s. Using temp directory.", LOG_DIR, e
    )
    LOG_DIR = tempfile.gettempdir()
    ERROR_LOG_FILE = os.path.join(LOG_DIR, "aiservice_errors.log")
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        _log_dir_available = True
    except OSError:
        logger.warning("Cannot create log directory, file logging disabled")
        _log_dir_available = False


_error_logger = logging.getLogger("aiservice.error")
if not _error_logger.handlers:
    if _log_dir_available:
        try:
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
        except OSError as e:
            logger.warning("Cannot create error log file, using console only: %s", e)
            # Fall back to console logging
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(message)s")
            handler.setFormatter(formatter)
            _error_logger.addHandler(handler)
            _error_logger.setLevel(logging.ERROR)
            _error_logger.propagate = False
    else:
        # No file logging available, use console only
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        _error_logger.addHandler(handler)
        _error_logger.setLevel(logging.ERROR)
        _error_logger.propagate = False


_event_loggers: Dict[str, logging.Logger] = {}


def _get_event_logger(log_file: str) -> logging.Logger:
    logger_inst = _event_loggers.get(log_file)
    if logger_inst is not None:
        for handler in list(logger_inst.handlers):
            if isinstance(handler, RotatingFileHandler) and not os.path.exists(
                handler.baseFilename
            ):
                handler.close()
                logger_inst.removeHandler(handler)
                logger_inst = None
                break
        if logger_inst is not None:
            return logger_inst
    if logger_inst is None:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            handler = RotatingFileHandler(
                log_file,
                maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            formatter = logging.Formatter("%(message)s")
            handler.setFormatter(formatter)
            logger_inst = logging.getLogger(f"event.{log_file}")
            logger_inst.addHandler(handler)
            logger_inst.setLevel(logging.INFO)
            logger_inst.propagate = False
        except OSError as e:
            # Fall back to console logging if file logging fails
            logger.warning(
                "Cannot create event log file %s: %s. Using console.", log_file, e
            )
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(message)s")
            handler.setFormatter(formatter)
            logger_inst = logging.getLogger(f"event.{log_file}")
            logger_inst.addHandler(handler)
            logger_inst.setLevel(logging.INFO)
            logger_inst.propagate = False
        _event_loggers[log_file] = logger_inst
    return logger_inst


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


def inject_failure(probability: float) -> None:
    """Simulates a failure based on the given probability."""
    # Pseudorandom is fine here: this is deliberate, test-only fault injection.
    if random.random() < probability:  # nosec B311
        log_error("Simulating failure for resilience testing.")
        time.sleep(1)  # Simulate some work before failing
        raise Exception("Injected failure for resilience testing")
