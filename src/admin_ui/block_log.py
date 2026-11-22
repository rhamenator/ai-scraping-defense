"""Search, filter, page and export the block log for the admin Logs page (#1951)."""

import csv
import datetime
import io
import ipaddress
import json
import logging
import os
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Time ranges the Logs page offers, in seconds; None means no lower bound.
RANGES: dict[str, int | None] = {
    "1h": 3600,
    "24h": 86400,
    "7d": 7 * 86400,
    "30d": 30 * 86400,
    "all": None,
}
DEFAULT_RANGE = "all"
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
MAX_QUERY_LENGTH = 100
# Only the newest lines are scanned so a very large log cannot exhaust memory or time.
MAX_SCAN_LINES = 100_000
# Matches cannot exceed the scanned lines, so with a page size of 1 there are at most this many pages.
MAX_PAGE = MAX_SCAN_LINES
MAX_EXPORT_ROWS = 10_000
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class BlockLogResult:
    events: list[dict]  # the requested page, newest first
    total: int  # events matching the filter within the scanned window
    page: int
    page_size: int
    pages: int
    truncated: bool  # True when older lines were not scanned


def _parse_line(line: str) -> dict | None:
    """Return a normalised event, or None for a malformed line."""
    try:
        data = json.loads(line)
        stamp = data.get("timestamp")
        if not stamp:
            return None
        moment = datetime.datetime.fromisoformat(stamp)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=datetime.timezone.utc)
        raw_ip = data.get("ip_address")
        ip = str(ipaddress.ip_address(raw_ip)) if raw_ip else None
    except (ValueError, TypeError, AttributeError):
        return None
    reason = data.get("reason")
    return {
        "timestamp": stamp,
        "moment": moment,
        "ip": ip,
        "reason": reason if isinstance(reason, str) else ("" if reason is None else str(reason)),
    }


def _cutoff(range_key: str, now: datetime.datetime) -> datetime.datetime | None:
    seconds = RANGES[range_key]
    return None if seconds is None else now - datetime.timedelta(seconds=seconds)


def _read_tail(path: str) -> tuple[list[str], bool]:
    """The newest MAX_SCAN_LINES lines (oldest first) and whether older lines were left unread."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = deque(handle, maxlen=MAX_SCAN_LINES + 1)
    except OSError as exc:
        logger.error("Error reading block events log", exc_info=exc)
        return [], False
    truncated = len(lines) > MAX_SCAN_LINES
    if truncated:
        lines.popleft()
    return list(lines), truncated


def _matches(event: dict, cutoff: datetime.datetime | None, needle: str) -> bool:
    if cutoff is not None and event["moment"] < cutoff:
        return False
    if not needle:
        return True
    return needle in (event["ip"] or "").lower() or needle in event["reason"].lower()


def _matching_events(
    path: str, query: str, range_key: str, now: datetime.datetime
) -> tuple[list[dict], bool]:
    """All events in the scanned window that match, newest first, and whether the log was cut short."""
    if not os.path.exists(path):
        return [], False
    cutoff = _cutoff(range_key, now)
    needle = query.strip().lower()
    lines, truncated = _read_tail(path)
    events = (_parse_line(line) for line in reversed(lines))
    return [e for e in events if e is not None and _matches(e, cutoff, needle)], truncated


def query_events(
    path: str,
    query: str = "",
    range_key: str = DEFAULT_RANGE,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    now: datetime.datetime | None = None,
) -> BlockLogResult:
    if range_key not in RANGES:
        raise ValueError("unknown range")
    page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    page = max(1, min(int(page), MAX_PAGE))
    now = now or datetime.datetime.now(datetime.timezone.utc)
    matches, truncated = _matching_events(path, query, range_key, now)
    pages = max(1, -(-len(matches) // page_size))
    page = min(page, pages)
    start = (page - 1) * page_size
    return BlockLogResult(
        events=matches[start : start + page_size],
        total=len(matches),
        page=page,
        page_size=page_size,
        pages=pages,
        truncated=truncated,
    )


def csv_cell(value) -> str:
    """Neutralise spreadsheet formula injection: a cell that starts like a formula is prefixed with a quote."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def export_csv(
    path: str,
    query: str = "",
    range_key: str = DEFAULT_RANGE,
    now: datetime.datetime | None = None,
) -> str:
    """The current filter as CSV (newest first, at most MAX_EXPORT_ROWS rows)."""
    if range_key not in RANGES:
        raise ValueError("unknown range")
    now = now or datetime.datetime.now(datetime.timezone.utc)
    matches, _ = _matching_events(path, query, range_key, now)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["timestamp", "ip", "reason"])
    for event in matches[:MAX_EXPORT_ROWS]:
        writer.writerow([csv_cell(event["timestamp"]), csv_cell(event["ip"]), csv_cell(event["reason"])])
    return buffer.getvalue()
