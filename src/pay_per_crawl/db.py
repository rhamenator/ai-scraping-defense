import os
import sqlite3
from typing import Dict, Optional

DB_PATH = os.environ.get("CRAWLER_DB_PATH", "crawler_registry.db")


def init_db(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS crawlers (token TEXT PRIMARY KEY, name TEXT, purpose TEXT, balance REAL DEFAULT 0)"
    )
    conn.commit()
    conn.close()


def register_crawler(
    name: str, token: str, purpose: str, db_path: str = DB_PATH
) -> None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            (
                "INSERT OR REPLACE INTO crawlers(token, name, purpose, balance) "
                "VALUES(?,?,?, COALESCE((SELECT balance FROM crawlers WHERE token=?),0))"
            ),
            (token, name, purpose, token),
        )
        conn.commit()


def get_crawler(token: str, db_path: str = DB_PATH) -> Optional[Dict[str, str]]:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
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


def add_credit(token: str, amount: float, db_path: str = DB_PATH) -> None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE crawlers SET balance=COALESCE(balance,0)+? WHERE token=?",
            (amount, token),
        )
        conn.commit()


def charge(token: str, amount: float, db_path: str = DB_PATH) -> bool:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT balance FROM crawlers WHERE token=?", (token,))
        row = cur.fetchone()
        if not row:
            return False
        balance = row[0] or 0.0
        if balance < amount:
            return False
        new_balance = balance - amount
        conn.execute(
            "UPDATE crawlers SET balance=? WHERE token=?", (new_balance, token)
        )
        conn.commit()
        return True
