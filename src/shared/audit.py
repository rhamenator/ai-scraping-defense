import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .log_filter import configure_sensitive_logging

LOG_PATH = os.getenv("AUDIT_LOG_FILE", "/app/logs/audit.log")
_audit_log_available = False
try:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    _audit_log_available = True
except OSError as e:
    # In test or development environments, /app may not exist or be writable
    # Fall back to a temp directory or disable file logging
    import tempfile

    LOG_PATH = os.path.join(tempfile.gettempdir(), "audit.log")
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        _audit_log_available = True
    except OSError:
        logging.warning(
            "Cannot create audit log directory, audit logging to file disabled: %s", e
        )
        _audit_log_available = False

logger = logging.getLogger("audit")
if not logger.handlers:
    if _audit_log_available:
        try:
            Path(LOG_PATH).touch(exist_ok=True)
            try:
                os.chmod(LOG_PATH, 0o600)
            except OSError as e:
                logger.warning("Cannot set audit log file permissions: %s", e)
            handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3)
            formatter = logging.Formatter("%(asctime)s %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        except OSError as e:
            logging.warning(
                "Cannot set up audit file logger, using console only: %s", e
            )
            # Fall back to console logging
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
    else:
        # No file logging available, use console only
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

configure_sensitive_logging(logger)


def log_event(user: str, action: str, details: Optional[dict] = None) -> None:
    """Write an audit log entry."""
    msg = f"{user}\t{action}"
    if details:
        msg += "\t" + json.dumps(details, sort_keys=True)
    logger.info(msg)
