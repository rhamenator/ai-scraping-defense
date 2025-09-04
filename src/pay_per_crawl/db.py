import os
import sqlite3
from typing import Dict, Optional

DB_PATH = os.environ.get("CRAWLER_DB_PATH", "crawler_registry.db")

_CONNECTION: sqlite3.Connection | None = None
_DB_PATH = DB_PATH


def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Initialize the crawler database if it hasn't been already."""
    global _CONNECTION, _DB_PATH
    if _CONNECTION is not None and db_path != _DB_PATH:
        _CONNECTION.close()
        _CONNECTION = None
    if _CONNECTION is None:
        _CONNECTION = sqlite3.connect(db_path)
        _CONNECTION.execute(
            "CREATE TABLE IF NOT EXISTS crawlers (token TEXT PRIMARY KEY, name TEXT, purpose TEXT, balance REAL DEFAULT 0)"
        )
        _CONNECTION.commit()
        _DB_PATH = db_path
    return _CONNECTION


def _get_conn() -> sqlite3.Connection:
    if _CONNECTION is None:
        raise RuntimeError("Database not initialized. Call init_db first.")
    return _CONNECTION


def register_crawler(name: str, token: str, purpose: str) -> None:
    conn = _get_conn()
    conn.execute(
        (
            "INSERT OR REPLACE INTO crawlers(token, name, purpose, balance) "
            "VALUES(?,?,?, COALESCE((SELECT balance FROM crawlers WHERE token=?),0))"
        ),
        (token, name, purpose, token),
    )
    conn.commit()


def get_crawler(token: str) -> Optional[Dict[str, str]]:
    conn = _get_conn()
    cur = conn.execute(
        "SELECT token, name, purpose, balance FROM crawlers WHERE token=?",
        (token,),
    )
    row = cur.fetchone()
    if row:
        return {
            "token": row[0],
            "name": row[1],
            "purpose": row[2],
            "balance": row[3],
        }
    return None


def add_credit(token: str, amount: float) -> None:
    conn = _get_conn()
    conn.execute(
        "UPDATE crawlers SET balance=COALESCE(balance,0)+? WHERE token=?",
        (amount, token),
    )
    conn.commit()


def charge(token: str, amount: float) -> bool:
    conn = _get_conn()
    cur = conn.execute("SELECT balance FROM crawlers WHERE token=?", (token,))
    row = cur.fetchone()
    if not row:
        return False
    balance = row[0] or 0.0
    if balance < amount:
        return False
    new_balance = balance - amount
    conn.execute("UPDATE crawlers SET balance=? WHERE token=?", (new_balance, token))
    conn.commit()
    return True
