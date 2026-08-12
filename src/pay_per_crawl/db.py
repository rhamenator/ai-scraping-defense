import os
import sqlite3
import threading
from typing import Dict, Optional

from src.pay_per_crawl import blockchain
from src.pay_per_crawl.audit_identity import audit_token

DB_PATH = os.environ.get("CRAWLER_DB_PATH", "crawler_registry.db")

_CONNECTION: sqlite3.Connection | None = None
_DB_PATH = DB_PATH
_DB_LOCK = threading.RLock()


def log_to_blockchain(action: str, data: dict) -> None:
    """Append pay-per-crawl events to a hash-chained audit log."""
    if not blockchain.log_action(action, data):
        del data  # avoid logging or leaking payload details
        print(f"[Blockchain] Logging skipped for action: {action}")


def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Initialize the crawler database and attempt to setup blockchain logging."""
    global _CONNECTION, _DB_PATH
    if _CONNECTION is not None and db_path != _DB_PATH:
        try:
            _CONNECTION.close()
        finally:
            _CONNECTION = None
    if _CONNECTION is None:
        _CONNECTION = sqlite3.connect(db_path, check_same_thread=False)
        _CONNECTION.execute("PRAGMA journal_mode=WAL")
        _CONNECTION.execute("PRAGMA synchronous=NORMAL")
        _CONNECTION.execute("PRAGMA busy_timeout=5000")
        _CONNECTION.execute(
            "CREATE TABLE IF NOT EXISTS crawlers "
            "(token TEXT PRIMARY KEY, name TEXT, purpose TEXT, "
            "balance REAL DEFAULT 0)"
        )
        _CONNECTION.commit()
        _DB_PATH = db_path

        if blockchain.LOG_ENABLED:
            print("Blockchain logging enabled.")
    return _CONNECTION


def _get_conn() -> sqlite3.Connection:
    if _CONNECTION is None:
        raise RuntimeError("Database not initialized. Call init_db first.")
    return _CONNECTION


def register_crawler(name: str, token: str, purpose: str) -> None:
    with _DB_LOCK:
        conn = _get_conn()
        conn.execute(
            (
                "INSERT INTO crawlers(token, name, purpose, balance) VALUES(?,?,?,0) "
                "ON CONFLICT(token) DO UPDATE SET name=excluded.name, purpose=excluded.purpose"
            ),
            (token, name, purpose),
        )
        conn.commit()
    log_to_blockchain(
        "register_crawler",
        {"name": name, "token_hash": audit_token(token), "purpose": purpose},
    )


def get_crawler(token: str) -> Optional[Dict[str, str]]:
    with _DB_LOCK:
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


def add_credit(token: str, amount: float) -> bool:
    with _DB_LOCK:
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE crawlers SET balance=COALESCE(balance,0)+? WHERE token=?",
            (amount, token),
        )
        conn.commit()
    if cur.rowcount == 0:
        return False
    log_to_blockchain(
        "add_credit", {"token_hash": audit_token(token), "amount": amount}
    )
    return True


def charge(token: str, amount: float) -> bool:
    with _DB_LOCK:
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE crawlers SET balance=balance-? " "WHERE token=? AND balance>=?",
            (amount, token, amount),
        )
        conn.commit()
    if cur.rowcount == 0:
        return False
    log_to_blockchain("charge", {"token_hash": audit_token(token), "amount": amount})
    return True


def delete_crawler(token: str) -> bool:
    """Delete crawler data (GDPR right to be forgotten).

    This implements the GDPR right to erasure by removing all
    crawler registration data associated with the given token.

    Args:
        token: The crawler token to delete

    Returns:
        True if data was deleted, False if token not found
    """
    with _DB_LOCK:
        conn = _get_conn()
        cur = conn.execute("DELETE FROM crawlers WHERE token=?", (token,))
        conn.commit()
    return cur.rowcount > 0


def anonymize_crawler(token: str) -> bool:
    """Anonymize crawler data while preserving financial records.

    This is useful when deletion is not possible due to legal
    retention requirements for financial transactions.

    Args:
        token: The crawler token to anonymize

    Returns:
        True if data was anonymized, False if token not found
    """
    with _DB_LOCK:
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE crawlers SET name=?, purpose=? WHERE token=?",
            ("[REDACTED]", "[REDACTED]", token),
        )
        conn.commit()
    return cur.rowcount > 0
