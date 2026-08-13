"""This module wraps a simple SQLite database used to persist blocklist decisions
and related metadata for analysis and debugging."""

import logging
import os
import sqlite3
from contextlib import contextmanager

from src.shared.config import CONFIG
from src.shared.security_events import record_security_event

DEFAULT_DB_DIR = "/app/data"
DB_PATH = os.getenv(
    "DECISIONS_DB_PATH",
    os.path.join(DEFAULT_DB_DIR, "decisions.db"),
)

# Ensure the directory for the database exists so connecting does not fail
try:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
except OSError as e:
    # In test or development environments, /app may not exist or be writable
    # Fall back to a temp directory
    import tempfile

    logging.warning(
        "Cannot create decision DB in %s: %s. Using temp directory.", DB_PATH, e
    )
    DB_PATH = os.path.join(tempfile.gettempdir(), "decisions.db")
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    except OSError as e2:
        logging.error("Failed to create directory for decision DB: %s", e2)
        raise RuntimeError(f"Failed to create directory for decision DB: {e2}") from e2

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    ip TEXT,
    source TEXT,
    score REAL,
    is_bot INTEGER,
    action TEXT,
    timestamp TEXT,
    tls_ja3 TEXT,
    tls_ja4 TEXT,
    tls_fingerprint_source TEXT,
    tls_fingerprint_verified INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_decisions_tenant ON decisions (tenant_id);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(decisions)")}
    for name, definition in (
        ("tls_ja3", "TEXT"),
        ("tls_ja4", "TEXT"),
        ("tls_fingerprint_source", "TEXT"),
        ("tls_fingerprint_verified", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if name not in columns:
            conn.execute(f"ALTER TABLE decisions ADD COLUMN {name} {definition}")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def record_decision(
    ip: str,
    source: str,
    score: float,
    is_bot: int | None,
    action: str,
    timestamp: str,
    tenant_id: str | None = None,
    *,
    tls_ja3: str | None = None,
    tls_ja4: str | None = None,
    tls_fingerprint_source: str | None = None,
    tls_fingerprint_verified: bool = False,
) -> None:
    tid = tenant_id or CONFIG.TENANT_ID
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO decisions "
            "(tenant_id, ip, source, score, is_bot, action, timestamp, "
            "tls_ja3, tls_ja4, tls_fingerprint_source, "
            "tls_fingerprint_verified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tid,
                ip,
                source,
                score,
                None if is_bot is None else int(bool(is_bot)),
                action,
                timestamp,
                tls_ja3,
                tls_ja4,
                tls_fingerprint_source,
                int(tls_fingerprint_verified),
            ),
        )
    try:
        severity = "info"
        if "block" in action or "tarpit" in action:
            severity = "high"
        elif "throttle" in action:
            severity = "warning"
        record_security_event(
            "security_decision",
            actor=tid,
            action=action,
            source=source,
            severity=severity,
            payload={
                "tenant_id": tid,
                "ip": ip,
                "score": score,
                "is_bot": is_bot,
                "timestamp": timestamp,
                "tls_ja3": tls_ja3,
                "tls_ja4": tls_ja4,
                "tls_fingerprint_source": tls_fingerprint_source,
                "tls_fingerprint_verified": tls_fingerprint_verified,
            },
            created_at=timestamp,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning("Failed to persist decision security event: %s", exc)
