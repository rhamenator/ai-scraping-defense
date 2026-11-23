"""Off-by-default manual access request queue for the built-in CAPTCHA.

Allows visitors who cannot complete a challenge to submit an optional short plain-text
note for an admin to review. Enforces one pending request per IP, a configurable per-IP
cooldown, a global pending queue cap, a global submission rate cap, short retention, and
temporary IP allowlisting on approval.
"""

import json
import logging
import os
import secrets
import threading
import time
from typing import Any, Optional

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

logger = logging.getLogger(__name__)

MAX_NOTE_LENGTH = 200

_SUBMIT_LUA = """
local pending_key = KEYS[1]
local cd_key = KEYS[2]
local items_key = KEYS[3]
local rate_key = KEYS[4]

local req_id = ARGV[1]
local payload = ARGV[2]
local retention_s = tonumber(ARGV[3])
local cooldown_s = tonumber(ARGV[4])
local max_pending = tonumber(ARGV[5])
local global_rate = tonumber(ARGV[6])

if redis.call('EXISTS', pending_key) == 1 then
    return 'already_pending'
end
if redis.call('EXISTS', cd_key) == 1 then
    return 'cooldown'
end
if max_pending <= 0 then
    return 'paused'
end
local pending_count = 0
for _, v in ipairs(redis.call('HVALS', items_key)) do
    if string.find(v, '"status":"pending"', 1, true) then
        pending_count = pending_count + 1
    end
end
if pending_count >= max_pending then
    return 'paused'
end
if global_rate > 0 then
    local hits = redis.call('INCR', rate_key)
    if hits == 1 then
        redis.call('EXPIRE', rate_key, 60)
    end
    if hits > global_rate then
        return 'paused'
    end
end
redis.call('HSET', items_key, req_id, payload)
redis.call('SET', pending_key, req_id, 'EX', retention_s)
if cooldown_s > 0 then
    redis.call('SET', cd_key, '1', 'EX', cooldown_s)
end
return 'queued'
"""


def sanitize_note(note: str | None, max_length: int = MAX_NOTE_LENGTH) -> str:
    """Strip control characters and collapse whitespace, capped at ``max_length`` chars."""
    cleaned = " ".join((note or "").split())
    cleaned = "".join(ch for ch in cleaned if ch >= " " and ch != "\x7f")
    return cleaned[:max_length]


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, default)))
    except (TypeError, ValueError):
        return default


class AccessRequestStore:
    def __init__(self, backend: Optional[str] = None):
        self._mode = (backend or os.getenv("CAPTCHA_STORE", "auto")).lower()
        self._lock = threading.Lock()
        self._redis: Any = None
        self._redis_tried = False
        self._requests: dict[str, dict] = {}
        self._pending_by_ip: dict[str, str] = {}
        self._cooldowns: dict[str, float] = {}
        self._allowed_ips: dict[str, float] = {}
        self._global_window: tuple[float, int] = (0.0, 0)

    def _client(self) -> Any:
        if self._mode == "memory":
            return None
        if not self._redis_tried:
            self._redis_tried = True
            try:
                self._redis = get_redis_connection()
            except Exception as exc:  # noqa: BLE001
                logger.warning("AccessRequestStore: Redis unavailable (%s); using memory", exc)
        return self._redis

    @staticmethod
    def _key(kind: str, name: str = "") -> str:
        suffix = f":{name}" if name else ""
        return tenant_key(f"captcha:req:{kind}{suffix}")

    def _purge_memory_locked(self, now: float) -> None:
        for rid in [rid for rid, rec in self._requests.items() if rec["expires_at"] <= now]:
            rec = self._requests.pop(rid)
            if self._pending_by_ip.get(rec["ip"]) == rid:
                self._pending_by_ip.pop(rec["ip"], None)
        self._cooldowns = _prune_expiries(self._cooldowns, now)
        self._allowed_ips = _prune_expiries(self._allowed_ips, now)

    def is_temporarily_allowed(self, ip: str) -> bool:
        if not ip:
            return False
        redis = self._client()
        if redis is not None:
            return bool(redis.exists(self._key("allow", ip)))
        with self._lock:
            self._purge_memory_locked(time.time())
            return self._allowed_ips.get(ip, 0.0) > time.time()

    def is_paused(self) -> bool:
        max_pending = _env_int("CAPTCHA_REQUEST_MAX_PENDING", 100)
        if max_pending <= 0:
            return True
        return self.pending_count() >= max_pending

    def pending_count(self) -> int:
        return sum(1 for rec in self.list_requests() if rec.get("status") == "pending")

    def submit(self, ip: str, note: str = "") -> tuple[bool, str, Optional[dict]]:
        now = time.time()
        cooldown_s = _env_int("CAPTCHA_REQUEST_COOLDOWN_SECONDS", 3600)
        max_pending = _env_int("CAPTCHA_REQUEST_MAX_PENDING", 100)
        global_rate = _env_int("CAPTCHA_REQUEST_GLOBAL_RATE_PER_MINUTE", 20)
        retention_s = max(1, _env_int("CAPTCHA_REQUEST_RETENTION_DAYS", 7)) * 86400
        clean_note = sanitize_note(note)

        limits = {
            "cooldown_s": cooldown_s,
            "max_pending": max_pending,
            "global_rate": global_rate,
            "retention_s": retention_s,
        }
        redis = self._client()
        if redis is not None:
            return self._submit_redis(redis, ip, clean_note, now, limits)
        return self._submit_memory(ip, clean_note, now, cooldown_s, max_pending, global_rate, retention_s)

    def _memory_rejection(self, ip: str, now: float, max_pending: int, global_rate: int) -> Optional[str]:
        if ip in self._pending_by_ip:
            return "already_pending"
        if self._cooldowns.get(ip, 0.0) > now:
            return "cooldown"
        pending = sum(1 for rec in self._requests.values() if rec["status"] == "pending")
        if max_pending <= 0 or pending >= max_pending or not self._allow_global_memory(now, global_rate):
            return "paused"
        return None

    def _submit_memory(
        self, ip: str, note: str, now: float, cooldown_s: int, max_pending: int, global_rate: int, retention_s: int
    ) -> tuple[bool, str, Optional[dict]]:
        with self._lock:
            self._purge_memory_locked(now)
            rejection = self._memory_rejection(ip, now, max_pending, global_rate)
            if rejection:
                return False, rejection, None
            record = _build_record(ip, note, now, retention_s)
            self._requests[record["id"]] = record
            self._pending_by_ip[ip] = record["id"]
            if cooldown_s > 0:
                self._cooldowns[ip] = now + cooldown_s
            return True, "queued", dict(record)

    def _allow_global_memory(self, now: float, limit: int) -> bool:
        if limit <= 0:
            return True
        reset, count = self._global_window
        if reset < now:
            reset, count = now + 60.0, 0
        if count + 1 > limit:
            self._global_window = (reset, count)
            return False
        self._global_window = (reset, count + 1)
        return True

    def _submit_redis(
        self, redis: Any, ip: str, note: str, now: float, limits: dict[str, int]
    ) -> tuple[bool, str, Optional[dict]]:
        self._list_redis(redis, now)  # prune expired items before checking queue capacity
        record = _build_record(ip, note, now, limits["retention_s"])
        payload = json.dumps(record, separators=(",", ":"))
        script = redis.register_script(_SUBMIT_LUA)
        status = script(
            keys=[self._key("pending", ip), self._key("cd", ip), self._key("items"), self._key("rate")],
            args=[
                record["id"],
                payload,
                limits["retention_s"],
                limits["cooldown_s"],
                limits["max_pending"],
                limits["global_rate"],
            ],
        )
        status_str = status.decode() if isinstance(status, bytes) else str(status)
        if status_str != "queued":
            return False, status_str, None
        return True, "queued", dict(record)

    def _list_redis(self, redis: Any, now: float) -> list[dict]:
        raw_map = redis.hgetall(self._key("items")) or {}
        records: list[dict] = []
        expired: list[str] = []
        for raw_id, raw_val in raw_map.items():
            rid = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)
            val = raw_val.decode() if isinstance(raw_val, bytes) else str(raw_val)
            rec = json.loads(val)
            if rec.get("expires_at", 0) <= now:
                expired.append(rid)
            else:
                records.append(rec)
        if expired:
            redis.hdel(self._key("items"), *expired)
        records.sort(key=lambda r: r.get("created_at", 0), reverse=True)
        return records

    def list_requests(self, include_closed: bool = False) -> list[dict]:
        now = time.time()
        redis = self._client()
        if redis is not None:
            records = self._list_redis(redis, now)
        else:
            with self._lock:
                self._purge_memory_locked(now)
                records = sorted((dict(r) for r in self._requests.values()), key=lambda r: r["created_at"], reverse=True)
        if include_closed:
            return records
        return [r for r in records if r.get("status") == "pending"]

    def approve(self, request_id: str, actor: str = "admin") -> Optional[dict]:
        return self._decide(request_id, "approved", actor)

    def deny(self, request_id: str, actor: str = "admin") -> Optional[dict]:
        return self._decide(request_id, "denied", actor)

    def _decide(self, request_id: str, decision: str, actor: str) -> Optional[dict]:
        allow_ttl = max(60, _env_int("CAPTCHA_REQUEST_ALLOW_TTL_SECONDS", 86400))
        now = time.time()
        redis = self._client()
        if redis is not None:
            raw = redis.hget(self._key("items"), request_id)
            if not raw:
                return None
            rec = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            rec.update({"status": decision, "reviewed_by": actor, "reviewed_at": now})
            pipe = redis.pipeline(transaction=True)
            pipe.hset(self._key("items"), request_id, json.dumps(rec, separators=(",", ":")))
            pipe.delete(self._key("pending", rec["ip"]))
            if decision == "approved":
                pipe.set(self._key("allow", rec["ip"]), "1", ex=allow_ttl)
            pipe.execute()
            return rec
        with self._lock:
            self._purge_memory_locked(now)
            rec = self._requests.get(request_id)
            if not rec:
                return None
            rec.update({"status": decision, "reviewed_by": actor, "reviewed_at": now})
            if self._pending_by_ip.get(rec["ip"]) == request_id:
                self._pending_by_ip.pop(rec["ip"], None)
            if decision == "approved":
                self._allowed_ips[rec["ip"]] = now + allow_ttl
            return dict(rec)

    def digest_summary(self) -> dict:
        pending = self.list_requests(include_closed=False)
        return {
            "pending_count": len(pending),
            "paused": self.is_paused(),
        }


def _prune_expiries(mapping: dict[str, float], now: float) -> dict[str, float]:
    return {key: ts for key, ts in mapping.items() if ts > now}


def _build_record(ip: str, note: str, now: float, retention_s: int) -> dict:
    return {
        "id": secrets.token_hex(8),
        "ip": ip,
        "note": note,
        "status": "pending",
        "created_at": now,
        "expires_at": now + retention_s,
    }
