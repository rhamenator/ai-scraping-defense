"""The one place that decides how a blocked IP is stored, read and removed (#1902).

The edge (``nginx/lua/blocklist.lua``) refuses a request when the key ``<tenant>:blocklist:ip:<ip>`` exists in the
blocklist database (``REDIS_DB_BLOCKLIST``). Every writer therefore uses exactly that key and database: the admin UI,
the signed webhook, the tarpit and the escalation engine. Keys carry a TTL for automated blocks and no expiry for blocks
an administrator or a signed webhook asked for explicitly. IPv4-mapped IPv6 addresses are stored as IPv4.

Earlier releases wrote some blocks as members of a Redis set (``<tenant>:blocklist``, in the default database for the
admin UI) and some as ``<tenant>:blocklist:<ip>`` (the tarpit). The edge never read those, so such blocks did nothing.
``migrate_legacy`` moves them to the real key and ``unblock`` also clears any legacy copy.
"""

import datetime
import ipaddress
import json
import logging
from typing import Any, Iterator, Optional

from redis.exceptions import RedisError

from src.shared.config import CONFIG, tenant_key
from src.shared.redis_client import get_redis_connection

logger = logging.getLogger(__name__)

_SCAN_COUNT = 1000
_MAX_LISTED = 10000


def block_key_prefix() -> str:
    return tenant_key("blocklist:ip:")


def normalize_ip(ip: str) -> str:
    """Canonical text form of an address; raises ValueError if it is not an IP."""
    parsed = ipaddress.ip_address(str(ip).strip())
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped:
        parsed = parsed.ipv4_mapped
    return str(parsed)


def block_key(ip: str) -> str:
    return f"{block_key_prefix()}{normalize_ip(ip)}"


def connection() -> Any:
    """A connection to the blocklist database, the one the edge reads."""
    return get_redis_connection(db_number=CONFIG.REDIS_DB_BLOCKLIST)


def _metadata(reason: str, source: str, details: Optional[dict]) -> str:
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    return json.dumps(
        {"reason": reason, "source": source, "timestamp_utc": stamp, "details": details or {}}
    )


def block(
    ip: str,
    reason: str,
    *,
    source: str,
    ttl_seconds: Optional[int] = None,
    details: Optional[dict] = None,
    conn: Any = None,
) -> bool:
    """Block ``ip`` for the edge. ``ttl_seconds`` of None or 0 means no expiry.

    Returns True only after reading the key back, so success means the edge will see it.
    """
    try:
        key = block_key(ip)
    except ValueError:
        logger.warning("Refusing to block invalid IP %r", ip)
        return False
    conn = conn if conn is not None else connection()
    if not conn:
        logger.error("Blocklist database unavailable; %s not blocked", ip)
        return False
    payload = _metadata(reason, source, details)
    try:
        if ttl_seconds and ttl_seconds > 0:
            if _is_permanent(conn, key):
                # An automated, expiring block never replaces one an administrator or a signed webhook made permanent.
                return True
            conn.setex(key, int(ttl_seconds), payload)
        else:
            conn.set(key, payload)
        return bool(conn.exists(key))
    except RedisError as exc:
        logger.error("Could not block %s: %s", ip, exc)
        return False


def _is_permanent(conn: Any, key: str) -> bool:
    """True when the key exists and has no expiry (Redis TTL -1)."""
    return bool(conn.exists(key)) and conn.ttl(key) == -1


def _legacy_keys(ip: str) -> tuple[str, str]:
    return tenant_key("blocklist"), tenant_key(f"blocklist:{ip}")


def unblock(ip: str, *, conn: Any = None, legacy_conns: tuple = ()) -> bool:
    """Remove the block for ``ip`` (and any legacy copy). True if the address is no longer blocked.

    ``legacy_conns`` are other databases that may still hold the old set (the admin UI used the default database); the
    entry is cleared there too, so a later migration cannot bring a block back that was just lifted.
    """
    try:
        normalized = normalize_ip(ip)
    except ValueError:
        return False
    conn = conn if conn is not None else connection()
    if not conn:
        return False
    legacy_set, legacy_key = _legacy_keys(normalized)
    try:
        conn.delete(block_key(normalized), legacy_key)
        for other in (conn, *(c for c in legacy_conns if c)):
            other.srem(legacy_set, normalized)
            other.delete(legacy_key)
        return not conn.exists(block_key(normalized))
    except RedisError as exc:
        logger.error("Could not unblock %s: %s", ip, exc)
        return False


def is_blocked(ip: str, *, conn: Any = None) -> bool:
    conn = conn if conn is not None else connection()
    try:
        return bool(conn and conn.exists(block_key(ip)))
    except (RedisError, ValueError):
        return False


def _decode(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def iter_blocked(conn: Any = None) -> Iterator[tuple[str, int]]:
    """Yield ``(ip, ttl_seconds)`` for every active block; ttl is -1 for blocks without expiry."""
    conn = conn if conn is not None else connection()
    if not conn:
        return
    prefix = block_key_prefix()
    for count, raw in enumerate(conn.scan_iter(match=f"{prefix}*", count=_SCAN_COUNT)):
        if count >= _MAX_LISTED:
            return
        key = _decode(raw)
        yield key[len(prefix):], int(conn.ttl(key))


def list_blocked(conn: Any = None) -> list[str]:
    return sorted(ip for ip, _ttl in iter_blocked(conn))


def counts(conn: Any = None) -> dict[str, int]:
    """Total blocks and how many of them expire."""
    total = temporary = 0
    for _ip, ttl in iter_blocked(conn):
        total += 1
        temporary += ttl >= 0
    return {"blocked": total, "temporary": temporary}


def _legacy_set_members(conn: Any) -> set[str]:
    members = conn.smembers(tenant_key("blocklist")) or set()
    return {_decode(m) for m in members} if isinstance(members, (set, list)) else set()


def _legacy_tarpit_keys(conn: Any) -> Iterator[str]:
    prefix, current = tenant_key("blocklist:"), block_key_prefix()
    for raw in conn.scan_iter(match=f"{prefix}*", count=_SCAN_COUNT):
        key = _decode(raw)
        if not key.startswith(current):
            yield key


def migrate_legacy(*, conn: Any = None, extra_conns: tuple = ()) -> int:
    """Move blocks written in the old shapes to the real key. Idempotent; returns how many were moved.

    ``extra_conns`` are other databases that may hold the old set (the admin UI used the default database).
    """
    conn = conn if conn is not None else connection()
    if not conn:
        return 0
    moved = 0
    for source in (conn, *extra_conns):
        try:
            moved += _migrate_set(source, conn) + _migrate_tarpit_keys(source, conn)
        except RedisError as exc:
            logger.error("Legacy blocklist migration stopped: %s", exc)
    if moved:
        logger.warning("Migrated %d legacy blocklist entr%s to the edge key", moved, "y" if moved == 1 else "ies")
    return moved


def _migrate_set(source: Any, target: Any) -> int:
    moved = 0
    for member in _legacy_set_members(source):
        if block(member, "migrated from the legacy blocklist set", source="migration", conn=target):
            source.srem(tenant_key("blocklist"), member)
            moved += 1
    return moved


def _migrate_tarpit_keys(source: Any, target: Any) -> int:
    moved = 0
    prefix = tenant_key("blocklist:")
    for key in list(_legacy_tarpit_keys(source)):
        ip = key[len(prefix):]
        ttl = int(source.ttl(key))
        if ttl == -2:  # the key expired after it was listed: nothing left to migrate
            continue
        # -1 is a key with no expiry; 0 means under a second is left, so keep a bounded one-second expiry.
        ttl_seconds = None if ttl == -1 else max(ttl, 1)
        reason = _decode(source.get(key) or "migrated from a legacy tarpit key")
        if block(ip, reason, source="migration", ttl_seconds=ttl_seconds, conn=target):
            source.delete(key)
            moved += 1
    return moved
