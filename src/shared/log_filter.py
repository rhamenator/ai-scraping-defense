import logging
import re
from typing import List, Tuple

_REPLACEMENTS: List[Tuple[re.Pattern[str], str]] = [
    # IPv4 addresses
    (
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
        ),
        "[REDACTED_IP]",
    ),
    # API keys and tokens
    (
        re.compile(r"(?i)(api[_-]?key|token|authorization)[:=]\s*[^\s]+"),
        r"\1=<redacted>",
    ),
    # Passwords
    (
        re.compile(r"(?i)(password|passwd|pwd)[:=]\s*[^\s]+"),
        r"\1=<redacted>",
    ),
]


def _mask(message: str) -> str:
    for pattern, repl in _REPLACEMENTS:
        message = pattern.sub(repl, message)
    return message


class SensitiveDataFilter(logging.Filter):
    """Mask sensitive data such as IPs, API keys, and passwords."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - simple
        message = record.getMessage()
        masked = _mask(message)
        record.msg = masked
        record.args = ()
        return True


_FILTER = SensitiveDataFilter()


def apply_sensitive_data_filter() -> None:
    """Attach the sensitive data filter to all loggers."""

    root_logger = logging.getLogger()
    if _FILTER not in root_logger.filters:
        root_logger.addFilter(_FILTER)

    for name in list(logging.root.manager.loggerDict):
        logger = logging.getLogger(name)
        if _FILTER not in logger.filters:
            logger.addFilter(_FILTER)

    _orig_get_logger = logging.getLogger

    def get_logger(name: str | None = None) -> logging.Logger:
        logger = _orig_get_logger(name)
        if _FILTER not in logger.filters:
            logger.addFilter(_FILTER)
        return logger

    logging.getLogger = get_logger
