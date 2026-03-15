"""Shared runtime containment helpers for throttling suspicious IPs."""

from __future__ import annotations

import datetime
import ipaddress
import json
import logging
import os
from typing import Any

from src.shared.config import CONFIG, tenant_key
from src.shared.redis_client import get_redis_connection

logger = logging.getLogger(__name__)

THROTTLE_KEY_PREFIX = tenant_key("throttle:ip:")
THROTTLE_TTL_SECONDS = int(os.getenv("THROTTLE_TTL_SECONDS", "900"))
THROTTLE_RATE_LIMIT_PER_MINUTE = int(os.getenv("THROTTLE_RATE_LIMIT_PER_MINUTE", "10"))


def _validate_ip(ip_address: str) -> bool:
    try:
        ipaddress.ip_address(ip_address)
        return True
    except ValueError:
        logger.error("Invalid IP address for throttle action: %s", ip_address)
        return False


def apply_ip_throttle(
    ip_address: str,
    *,
    reason: str,
    score: float,
    source: str,
    ttl_seconds: int | None = None,
    rate_limit_per_minute: int | None = None,
    extra_details: dict[str, Any] | None = None,
) -> bool:
    """Persist a temporary throttle instruction for an IP in Redis."""

    if not ip_address or not _validate_ip(ip_address):
        return False

    redis_conn = get_redis_connection(db_number=CONFIG.REDIS_DB_BLOCKLIST)
    if not redis_conn:
        logger.error("Redis unavailable. Cannot throttle IP %s.", ip_address)
        return False

    effective_ttl = ttl_seconds or THROTTLE_TTL_SECONDS
    effective_limit = rate_limit_per_minute or THROTTLE_RATE_LIMIT_PER_MINUTE
    key = f"{THROTTLE_KEY_PREFIX}{ip_address}"
    payload = {
        "reason": reason,
        "score": score,
        "source": source,
        "rate_limit_per_minute": effective_limit,
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "details": extra_details or {},
    }

    try:
        redis_conn.setex(key, effective_ttl, json.dumps(payload, sort_keys=True))
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to store throttle state for IP %s: %s", ip_address, exc)
        return False
    return True


def get_ip_throttle(ip_address: str) -> dict[str, Any] | None:
    """Return throttle metadata for an IP, including TTL when available."""

    if not ip_address or not _validate_ip(ip_address):
        return None

    redis_conn = get_redis_connection(db_number=CONFIG.REDIS_DB_BLOCKLIST)
    if not redis_conn:
        logger.error("Redis unavailable. Cannot inspect throttle for %s.", ip_address)
        return None

    key = f"{THROTTLE_KEY_PREFIX}{ip_address}"
    try:
        payload = redis_conn.get(key)
        if not payload:
            return None
        ttl_seconds = redis_conn.ttl(key)
        metadata = json.loads(payload)
        if isinstance(metadata, dict):
            metadata["ttl_seconds"] = ttl_seconds
            return metadata
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to read throttle state for IP %s: %s", ip_address, exc)
    return None
