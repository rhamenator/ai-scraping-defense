"""Durable security-event storage and export helpers."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

DEFAULT_DB_DIR = "/app/data"
DB_PATH = os.getenv(
    "SECURITY_EVENTS_DB_PATH",
    os.path.join(DEFAULT_DB_DIR, "security_events.db"),
)

logger = logging.getLogger(__name__)

try:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
except OSError as exc:
    logger.warning(
        "Cannot create security event DB in %s: %s. Using temp dir.", DB_PATH, exc
    )
    DB_PATH = os.path.join(tempfile.gettempdir(), "security_events.db")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT,
    source TEXT,
    severity TEXT NOT NULL,
    ip TEXT,
    path TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_security_events_created_at
    ON security_events (created_at);
CREATE INDEX IF NOT EXISTS idx_security_events_type
    ON security_events (event_type);
CREATE INDEX IF NOT EXISTS idx_security_events_source
    ON security_events (source);
"""

IP_FIELD_NAMES = {
    "client_ip",
    "forwarded_for",
    "ip",
    "ip_address",
    "remote_ip",
    "source_ip",
}
PATH_FIELD_NAMES = {"path", "request_path", "route"}
SENSITIVE_FIELD_TOKENS = (
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
    "webhook",
)


def _is_sensitive_field(field_name: str | None) -> bool:
    if not field_name:
        return False
    normalized = field_name.lower()
    return any(token in normalized for token in SENSITIVE_FIELD_TOKENS)


def redact_sensitive_data(value: Any, field_name: str | None = None) -> Any:
    """Redact secrets while preserving enough structure for investigation."""
    if isinstance(value, dict):
        return {key: redact_sensitive_data(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_data(item, field_name) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive_data(item, field_name) for item in value]
    if field_name and field_name.lower() in IP_FIELD_NAMES:
        return "[REDACTED_IP]"
    if _is_sensitive_field(field_name):
        return "<redacted>"
    return value


def _extract_first(payload: dict[str, Any], field_names: Iterable[str]) -> str | None:
    for field_name in field_names:
        value = payload.get(field_name)
        if isinstance(value, str) and value:
            return value
    return None


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def record_security_event(
    event_type: str,
    *,
    actor: str = "system",
    action: str | None = None,
    source: str | None = None,
    severity: str = "info",
    payload: Optional[dict[str, Any]] = None,
    created_at: str | None = None,
) -> int:
    """Persist a structured security event and return its row id."""
    event_payload = redact_sensitive_data(payload or {})
    event_created_at = created_at or datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO security_events (
                created_at,
                event_type,
                actor,
                action,
                source,
                severity,
                ip,
                path,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_created_at,
                event_type,
                actor,
                action,
                source,
                severity,
                _extract_first(event_payload, IP_FIELD_NAMES),
                _extract_first(event_payload, PATH_FIELD_NAMES),
                json.dumps(event_payload, sort_keys=True, default=str),
            ),
        )
        return int(cursor.lastrowid)


def load_security_events(
    *, limit: int = 1000, event_type: str | None = None
) -> list[dict[str, Any]]:
    """Load stored security events in newest-first order."""
    query = """
        SELECT
            id,
            created_at,
            event_type,
            actor,
            action,
            source,
            severity,
            ip,
            path,
            payload_json
        FROM security_events
    """
    parameters: list[Any] = []
    if event_type:
        query += " WHERE event_type = ?"
        parameters.append(event_type)
    query += " ORDER BY id DESC LIMIT ?"
    parameters.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, parameters).fetchall()

    events = []
    for row in reversed(rows):
        payload_json = row[9] or "{}"
        events.append(
            {
                "id": row[0],
                "created_at": row[1],
                "event_type": row[2],
                "actor": row[3],
                "action": row[4],
                "source": row[5],
                "severity": row[6],
                "ip": row[7],
                "path": row[8],
                "payload": json.loads(payload_json),
            }
        )
    return events


def export_security_events(
    *,
    output_path: str | None = None,
    limit: int = 1000,
    event_type: str | None = None,
) -> tuple[int, str]:
    """Export events as JSONL and optionally write them to disk."""
    events = load_security_events(limit=limit, event_type=event_type)
    jsonl = "\n".join(json.dumps(event, sort_keys=True) for event in events)
    if jsonl:
        jsonl += "\n"
    if output_path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(jsonl, encoding="utf-8")
        try:
            os.chmod(destination, 0o600)
        except OSError:
            logger.debug(
                "Unable to set restrictive permissions on %s",
                destination,
                exc_info=True,
            )
    return len(events), jsonl
