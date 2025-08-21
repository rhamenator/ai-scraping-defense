import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .log_filter import configure_sensitive_logging

LOG_PATH = os.getenv("AUDIT_LOG_FILE", "/app/logs/audit.log")
try:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
except OSError as e:
    logging.error("Cannot create audit log directory: %s", e)
    raise SystemExit(1)

logger = logging.getLogger("audit")
if not logger.handlers:
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
        logging.error("Cannot set up audit logger: %s", e)
        raise SystemExit(1)

configure_sensitive_logging(logger)


def log_event(user: str, action: str, details: Optional[dict] = None) -> None:
    """Write an audit log entry."""
    msg = f"{user}\t{action}"
    if details:
        msg += "\t" + json.dumps(details, sort_keys=True)
    logger.info(msg)
