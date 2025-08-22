"""Simple crawler registry for token-based authentication backed by Redis."""

from __future__ import annotations

from typing import Dict, Optional

from redis.exceptions import RedisError

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection


def _key(token: str) -> str:
    return tenant_key(f"crawler:token:{token}")


CRAWLER_TTL_SECONDS = 24 * 60 * 60


def register_crawler(name: str, token: str, purpose: str) -> bool:
    """Register or update a crawler token."""
    redis_conn = get_redis_connection()
    if not redis_conn:
        return False
    try:
        key = _key(token)
        redis_conn.hset(key, mapping={"name": name, "purpose": purpose})
        redis_conn.expire(key, CRAWLER_TTL_SECONDS)
    except RedisError:
        return False
    return True


def verify_crawler(token: str, purpose: str | None = None) -> bool:
    """Return True if the token exists and (optionally) matches the given purpose."""
    redis_conn = get_redis_connection()
    if not redis_conn:
        return False
    try:
        info = redis_conn.hgetall(_key(token))
    except RedisError:
        return False
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
    try:
        info = redis_conn.hgetall(_key(token))
    except RedisError:
        return None
    return info or None
