"""Minimal pay-per-crawl accounting backed by Redis."""

from __future__ import annotations

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

_default_price = 0.001
PRICES_KEY = tenant_key("crawler:prices")
USAGE_KEY = tenant_key("crawler:usage")


def set_price(purpose: str, price: float) -> None:
    """Set the crawl price for a specific purpose."""
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    redis_conn.hset(PRICES_KEY, purpose, max(0.0, price))


def record_crawl(token: str, purpose: str) -> float:
    """Record a crawl and return the charge for this request."""
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    raw = redis_conn.hget(PRICES_KEY, purpose)
    price = float(raw) if raw is not None else _default_price
    redis_conn.hincrbyfloat(USAGE_KEY, token, price)
    return price


def get_usage(token: str) -> float:
    """Return the current owed balance for a token."""
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    raw = redis_conn.hget(USAGE_KEY, token)
    return float(raw) if raw is not None else 0.0
