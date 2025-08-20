import datetime
import ipaddress
import json
import logging
import os
from typing import Optional

from redis.exceptions import ConnectionError, RedisError

from src.shared.config import CONFIG, tenant_key
from src.shared.redis_client import get_redis_connection as shared_get_redis_connection
from src.shared.utils import LOG_DIR, log_error, log_event

logger = logging.getLogger(__name__)

REDIS_HOST = CONFIG.REDIS_HOST
REDIS_PORT = CONFIG.REDIS_PORT
REDIS_DB_BLOCKLIST = CONFIG.REDIS_DB_BLOCKLIST
BLOCKLIST_KEY_PREFIX = tenant_key("blocklist:ip:")
BLOCKLIST_TTL_SECONDS = CONFIG.BLOCKLIST_TTL_SECONDS

BLOCK_LOG_FILE = os.path.join(LOG_DIR, "block_events.log")

BLOCKLISTING_ENABLED = False
_redis_client_blocklist = None


def get_redis_connection():
    """Return a Redis connection, creating it on first use with retries."""
    global _redis_client_blocklist, BLOCKLISTING_ENABLED

    if _redis_client_blocklist is None:
        try:
            _redis_client_blocklist = shared_get_redis_connection(
                db_number=REDIS_DB_BLOCKLIST
            )
            if _redis_client_blocklist:
                try:
                    _redis_client_blocklist.ping()
                    BLOCKLISTING_ENABLED = True
                    logger.info(
                        "Connected to Redis for blocklisting at %s:%s, DB: %s",
                        REDIS_HOST,
                        REDIS_PORT,
                        REDIS_DB_BLOCKLIST,
                    )
                except (ConnectionError, RedisError) as e:
                    logger.error(
                        "Redis ping failed for Blocklisting: %s. Blocklisting disabled.",
                        e,
                    )
                    BLOCKLISTING_ENABLED = False
                    _redis_client_blocklist = None
            else:
                logger.error(
                    "Redis connection for blocklisting returned None. Blocklisting disabled."
                )
                BLOCKLISTING_ENABLED = False
        except (ConnectionError, RedisError) as e:
            logger.error(
                "Redis connection failed for Blocklisting: %s. Blocklisting disabled.",
                e,
            )
            BLOCKLISTING_ENABLED = False
            _redis_client_blocklist = None
        except Exception as e:  # pragma: no cover - unexpected
            logger.error(
                "Unexpected error connecting to Redis for Blocklisting: %s. Blocklisting disabled.",
                e,
            )
            BLOCKLISTING_ENABLED = False
            _redis_client_blocklist = None
    return _redis_client_blocklist


def add_ip_to_blocklist(
    ip_address: str, reason: str, event_details: Optional[dict] = None
) -> bool:
    redis_conn = get_redis_connection()
    if (
        not BLOCKLISTING_ENABLED
        or not redis_conn
        or not ip_address
        or ip_address == "unknown"
    ):
        if ip_address == "unknown":
            logger.warning(
                "Attempted to blocklist 'unknown' IP. Reason: %s. Details: %s",
                reason,
                event_details,
            )
        return False
    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        logger.warning(
            "Attempted to blocklist invalid IP %s. Reason: %s. Details: %s",
            ip_address,
            reason,
            event_details,
        )
        return False
    try:
        block_key = f"{BLOCKLIST_KEY_PREFIX}{ip_address}"
        block_metadata = json.dumps(
            {
                "reason": reason,
                "timestamp_utc": datetime.datetime.now(datetime.timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "details": event_details or {},
            }
        )
        redis_conn.setex(block_key, BLOCKLIST_TTL_SECONDS, block_metadata)
        logger.info(
            "Added/Refreshed IP %s to Redis blocklist (Key: %s) with TTL %ss. Reason: %s",
            ip_address,
            block_key,
            BLOCKLIST_TTL_SECONDS,
            reason,
        )
        log_event(
            BLOCK_LOG_FILE,
            "BLOCKLIST_ADD_TTL",
            {
                "ip_address": ip_address,
                "reason": reason,
                "ttl_seconds": BLOCKLIST_TTL_SECONDS,
                "details": event_details,
            },
        )
        return True
    except RedisError as e:
        log_error(f"Redis error setting blocklist key for IP {ip_address}", e)
    except Exception as e:  # pragma: no cover - unexpected
        log_error(f"Unexpected error setting blocklist key for IP {ip_address}", e)
    return False
