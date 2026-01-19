import json
import logging
import secrets
import time
from typing import Any

import bcrypt
from redis.exceptions import RedisError

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

logger = logging.getLogger(__name__)

BACKUP_CODE_LENGTH = 8
BACKUP_CODE_COUNT = 10
BACKUP_CODE_TTL = 90 * 24 * 3600


def _backup_codes_key(user: str) -> str:
    return tenant_key(f"admin_ui:mfa:backup_codes:{user}")


def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> list[str]:
    codes: list[str] = []
    for _ in range(count):
        code = "".join(str(secrets.randbelow(10)) for _ in range(BACKUP_CODE_LENGTH))
        codes.append(code)
    return codes


def _hash_backup_code(code: str) -> str:
    return bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()


def store_backup_codes(user: str, codes: list[str]) -> bool:
    redis_conn = get_redis_connection()
    if not redis_conn:
        logger.error("Redis unavailable, cannot store backup codes")
        return False
    try:
        payload = {
            "codes": [_hash_backup_code(code) for code in codes],
            "used": [False for _ in codes],
            "created_at": time.time(),
        }
        redis_conn.set(_backup_codes_key(user), json.dumps(payload), ex=BACKUP_CODE_TTL)
        return True
    except RedisError as exc:
        logger.error("Failed to store backup codes: %s", exc)
        return False


def _load_backup_payload(redis_conn: Any, user: str) -> dict | None:
    raw = redis_conn.get(_backup_codes_key(user))
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def verify_backup_code(user: str, code: str) -> bool:
    redis_conn = get_redis_connection()
    if not redis_conn:
        logger.error("Redis unavailable, cannot verify backup codes")
        return False
    try:
        data = _load_backup_payload(redis_conn, user)
        if not data:
            return False
        codes = data.get("codes") or []
        used = data.get("used") or [False for _ in codes]
        for index, hashed in enumerate(codes):
            if index >= len(used) or used[index]:
                continue
            if bcrypt.checkpw(code.encode(), hashed.encode()):
                used[index] = True
                data["used"] = used
                ttl = redis_conn.ttl(_backup_codes_key(user))
                if ttl is None or ttl <= 0:
                    ttl = BACKUP_CODE_TTL
                redis_conn.set(_backup_codes_key(user), json.dumps(data), ex=int(ttl))
                return True
        return False
    except RedisError as exc:
        logger.error("Failed to verify backup code: %s", exc)
        return False


def get_remaining_backup_codes_count(user: str) -> int:
    redis_conn = get_redis_connection()
    if not redis_conn:
        return 0
    try:
        data = _load_backup_payload(redis_conn, user)
        if not data:
            return 0
        used = data.get("used") or []
        return sum(1 for status in used if not status)
    except RedisError:
        return 0
