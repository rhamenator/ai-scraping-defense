"""SQLite storage for request decisions.

This module wraps a simple SQLite database used to persist blocklist
decisions and related metadata for analysis and debugging.
"""

import os
import sqlite3
from contextlib import contextmanager
from src.shared.config import CONFIG

DEFAULT_DB_DIR = "/app/data"
DB_PATH = os.getenv(
    "DECISIONS_DB_PATH",
    os.path.join(DEFAULT_DB_DIR, "decisions.db"),
)

# Ensure the directory for the database exists so connecting does not fail
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    ip TEXT,
    source TEXT,
    score REAL,
    is_bot INTEGER,
    action TEXT,
    timestamp TEXT
);
CREATE INDEX IF NOT EXISTS idx_decisions_tenant ON decisions (tenant_id);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
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
) -> None:
    tid = tenant_id or CONFIG.TENANT_ID
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO decisions (tenant_id, ip, source, score, is_bot, action, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                tid,
                ip,
                source,
                score,
                None if is_bot is None else int(bool(is_bot)),
                action,
                timestamp,
            ),
        )
