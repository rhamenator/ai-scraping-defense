"""Minimal pay-per-crawl accounting backed by Redis."""

from __future__ import annotations

from fastapi import HTTPException, status
from redis.exceptions import RedisError

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

_default_price = 0.001
PRICES_KEY = tenant_key("crawler:prices")
USAGE_KEY = tenant_key("crawler:usage")


def set_price(purpose: str, price: float) -> None:
    """Set the crawl price for a specific purpose."""
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Redis unavailable")
    try:
        redis_conn.hset(PRICES_KEY, purpose, max(0.0, price))
    except RedisError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Redis unavailable")


def record_crawl(token: str, purpose: str) -> float:
    """Record a crawl and return the charge for this request."""
    redis_conn = get_redis_connection()
    if not redis_conn:
        return _default_price
    try:
        raw = redis_conn.hget(PRICES_KEY, purpose)
    except RedisError:
        raw = None
    if raw is not None:
        try:
            price = float(raw)
        except ValueError:
            price = _default_price
    else:
        price = _default_price
    try:
        redis_conn.hincrbyfloat(USAGE_KEY, token, price)
    except RedisError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Redis unavailable")
    return price


def get_usage(token: str) -> float:
    """Return the current owed balance for a token."""
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Redis unavailable")
    try:
        raw = redis_conn.hget(USAGE_KEY, token)
    except RedisError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Redis unavailable")
    if raw is not None:
        try:
            return float(raw)
        except ValueError:
            return 0.0
    else:
        return 0.0
