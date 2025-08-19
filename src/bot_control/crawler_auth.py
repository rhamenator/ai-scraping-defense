"""Simple crawler registry for token-based authentication backed by Redis."""

from __future__ import annotations

from typing import Dict, Optional

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection


def _key(token: str) -> str:
    return tenant_key(f"crawler:token:{token}")


def register_crawler(name: str, token: str, purpose: str) -> None:
    """Register or update a crawler token."""
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    redis_conn.hset(_key(token), mapping={"name": name, "purpose": purpose})


def verify_crawler(token: str, purpose: str | None = None) -> bool:
    """Return True if the token exists and (optionally) matches the given purpose."""
    redis_conn = get_redis_connection()
    if not redis_conn:
        return False
    info = redis_conn.hgetall(_key(token))
    if not info:
        return False
    if purpose and info.get("purpose") != purpose:
        return False
    return True


def get_crawler_info(token: str) -> Optional[Dict[str, str]]:
    """Return crawler info if registered."""
    redis_conn = get_redis_connection()
    if not redis_conn:
        return None
    info = redis_conn.hgetall(_key(token))
    return info or None
