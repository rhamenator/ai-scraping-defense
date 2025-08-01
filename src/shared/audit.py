import json
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_PATH = os.getenv("AUDIT_LOG_FILE", "/app/logs/audit.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

logger = logging.getLogger("audit")
if not logger.handlers:
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3)
    formatter = logging.Formatter("%(asctime)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def log_event(user: str, action: str, details: dict | None = None) -> None:
    """Write an audit log entry."""
    msg = f"{user}\t{action}"
    if details:
        msg += "\t" + json.dumps(details, sort_keys=True)
    logger.info(msg)
