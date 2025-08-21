"""Utilities for masking sensitive data in log messages."""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Set, Tuple

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


class SensitiveDataFormatter(logging.Formatter):
    """Formatter that masks sensitive data from log records."""

    def __init__(self, base_formatter: Optional[logging.Formatter] = None):
        super().__init__()
        self._base = base_formatter

    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - simple
        if self._base is not None:
            formatted = self._base.format(record)
        else:
            formatted = super().format(record)
        return _mask(formatted)


_CONFIGURED_HANDLERS: Set[int] = set()


def _ensure_formatter(handler: logging.Handler) -> None:
    handler_id = id(handler)
    if handler_id in _CONFIGURED_HANDLERS:
        return
    formatter = handler.formatter
    if isinstance(formatter, SensitiveDataFormatter):
        _CONFIGURED_HANDLERS.add(handler_id)
        return
    handler.setFormatter(SensitiveDataFormatter(formatter))
    _CONFIGURED_HANDLERS.add(handler_id)


def configure_sensitive_logging(
    logger: Optional[logging.Logger] = None, *, include_existing_handlers: bool = True
) -> None:
    """Apply masking to handlers of ``logger`` or the root logger by default."""

    if logger is None:
        loggers = [logging.getLogger()] + [
            logging.getLogger(name) for name in logging.root.manager.loggerDict
        ]
    else:
        loggers = [logger]

    for log in loggers:
        if include_existing_handlers:
            for handler in log.handlers:
                _ensure_formatter(handler)
