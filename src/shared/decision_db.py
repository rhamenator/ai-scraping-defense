import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("DECISIONS_DB_PATH", "/app/data/decisions.db")

# Ensure the directory for the database exists so connecting does not fail
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT,
    source TEXT,
    score REAL,
    is_bot INTEGER,
    action TEXT,
    timestamp TEXT
);
"""

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def record_decision(ip: str, source: str, score: float, is_bot: int | None, action: str, timestamp: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO decisions (ip, source, score, is_bot, action, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (ip, source, score, None if is_bot is None else int(bool(is_bot)), action, timestamp),
        )
