import os
import sqlite3
from typing import Dict, Optional

DB_PATH = os.environ.get("CRAWLER_DB_PATH", "crawler_registry.db")

_CONNECTION: sqlite3.Connection | None = None
_DB_PATH = DB_PATH

def log_to_blockchain(action: str, data: dict) -> None:
    """Placeholder for logging actions to a blockchain.

    In a real implementation, this would interact with a blockchain network.
    """
    # TODO: Implement actual blockchain logging using a library like web3.py
    # Example:
    # from web3 import Web3
    # w3 = Web3(Web3.HTTPProvider('http://localhost:8545'))
    # contract = w3.eth.contract(address='...', abi=...)  # Replace with your contract
    # tx_hash = contract.functions.logAction(action, str(data)).transact({'from': w3.eth.accounts[0]})
    # print(f'Transaction hash: {tx_hash.hex()}')
    print(f"[Blockchain] Logging action: {action} with data: {data}")


def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Initialize the crawler database and attempt to setup blockchain logging."""
    global _CONNECTION, _DB_PATH
    if _CONNECTION is not None and db_path != _DB_PATH:
        try:
            _CONNECTION.close()
        finally:
            _CONNECTION = None
    if _CONNECTION is None:
        _CONNECTION = sqlite3.connect(db_path)
        _CONNECTION.execute(
            "CREATE TABLE IF NOT EXISTS crawlers (token TEXT PRIMARY KEY, name TEXT, purpose TEXT, balance REAL DEFAULT 0)"
        )
        _CONNECTION.commit()
        _DB_PATH = db_path

        # Attempt to setup blockchain logging (replace with actual logic if needed)
        try:
            # TODO: Add initialization logic for blockchain connection
            print("Blockchain logging setup initialized.")  # Replace with actual initialization
        except Exception as e:
            print(f"Failed to initialize blockchain logging: {e}")
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
    log_to_blockchain("register_crawler", {"name": name, "token": token, "purpose": purpose})


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
    log_to_blockchain("add_credit", {"token": token, "amount": amount})


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
    log_to_blockchain("charge", {"token": token, "amount": amount})
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
    conn = _get_conn()
    cur = conn.execute(
        "UPDATE crawlers SET name=?, purpose=? WHERE token=?",
        ("[REDACTED]", "[REDACTED]", token),
    )
    conn.commit()
    return cur.rowcount > 0
