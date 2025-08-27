import asyncio
import datetime
import ipaddress
import json
import logging
import os
from collections import deque

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from src.shared.audit import log_event
from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection
from src.shared.request_utils import read_json_body

from . import metrics
from .auth import require_admin, require_auth

logger = logging.getLogger(__name__)

BLOCK_LOG_FILE = os.getenv("BLOCK_LOG_FILE", "/app/logs/block_events.log")

router = APIRouter()


def _load_recent_block_events(limit: int = 5) -> list[dict]:
    """Load the most recent block events from the log file."""
    if not os.path.exists(BLOCK_LOG_FILE):
        return []
    events: list[dict] = []
    try:
        with open(BLOCK_LOG_FILE, "r", encoding="utf-8") as f:
            lines = deque(f, maxlen=limit)
        for line in lines:
            try:
                data = json.loads(line)
                ts = data.get("timestamp")
                if not ts:
                    logger.debug("Missing timestamp in block event: %s", line)
                    continue
                try:
                    _ = datetime.datetime.fromisoformat(ts)
                except ValueError:
                    logger.debug("Invalid timestamp in block event: %s", ts)
                    continue

                ip_val = data.get("ip_address")
                try:
                    normalized_ip = (
                        str(ipaddress.ip_address(ip_val)) if ip_val else None
                    )
                except ValueError:
                    logger.warning("Invalid IP address in block event: %s", ip_val)
                    continue

                events.append(
                    {
                        "timestamp": ts,
                        "ip": normalized_ip,
                        "reason": data.get("reason"),
                    }
                )
            except Exception as exc:
                logger.error("Failed to parse block event line: %s", line, exc_info=exc)
                continue
    except Exception as exc:
        logger.error("Error reading block events log", exc_info=exc)
        return []
    return events


# Exposed for tests so they can patch the behaviour
_load_recent_block_events_func = _load_recent_block_events


@router.get("/block_stats")
async def block_stats(user: str = Depends(require_auth)):
    """Return blocklist counts and bot detection statistics."""
    metrics_dict = {}
    try:
        metrics_dict = metrics._get_metrics_dict_func()
    except Exception as exc:
        logger.error("Failed to load metrics", exc_info=exc)
        metrics_dict = {}
    total_bots = sum(
        float(v) for k, v in metrics_dict.items() if k.startswith("bots_detected")
    )
    total_humans = sum(
        float(v) for k, v in metrics_dict.items() if k.startswith("humans_detected")
    )

    redis_conn = get_redis_connection()
    blocked_ips = set()
    temp_block_count = 0
    if redis_conn:
        try:
            blocked_ips = redis_conn.smembers(tenant_key("blocklist")) or set()
            pattern = tenant_key("blocklist:ip:*")
            cursor = 0
            temp_block_count = 0
            while True:
                cursor, keys = redis_conn.scan(cursor=cursor, match=pattern, count=1000)
                temp_block_count += len(keys)
                if cursor == 0:
                    break
        except RedisError as exc:
            logger.error("Error loading blocklist from redis", exc_info=exc)
            return JSONResponse(
                {"error": "Service temporarily unavailable"}, status_code=503
            )
        except Exception as exc:
            logger.error("Error loading blocklist from redis", exc_info=exc)

    recent_events = _load_recent_block_events_func(5)
    return JSONResponse(
        {
            "blocked_ip_count": len(blocked_ips),
            "temporary_block_count": temp_block_count,
            "total_bots_detected": total_bots,
            "total_humans_detected": total_humans,
            "recent_block_events": recent_events,
        }
    )


@router.get("/blocklist")
async def get_blocklist(user: str = Depends(require_auth)):
    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)

    try:
        blocklist_set = redis_conn.smembers(tenant_key("blocklist"))
        if asyncio.iscoroutine(blocklist_set):
            blocklist_set = await blocklist_set
    except RedisError as exc:
        logger.error("Error retrieving blocklist", exc_info=exc)
        return JSONResponse(
            {"error": "Service temporarily unavailable"}, status_code=503
        )

    if isinstance(blocklist_set, (set, list)):
        return JSONResponse(list(blocklist_set))

    logger.error(
        "Unexpected blocklist response type from Redis: %s",
        type(blocklist_set).__name__,
    )
    return JSONResponse({"error": "Redis returned invalid data"}, status_code=503)


@router.post("/block")
async def block_ip(request: Request, user: str = Depends(require_admin)):
    json_data = await read_json_body(request)
    if not json_data:
        return JSONResponse(
            {"error": "Invalid request, missing JSON body"}, status_code=400
        )

    ip = json_data.get("ip")
    if not ip:
        return JSONResponse({"error": "Invalid request, missing ip"}, status_code=400)
    try:
        normalized_ip = str(ipaddress.ip_address(ip))
    except ValueError:
        return JSONResponse({"error": "Invalid ip"}, status_code=400)

    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)

    try:
        redis_conn.sadd(tenant_key("blocklist"), normalized_ip)
    except RedisError as exc:
        logger.error("Error adding IP to blocklist", exc_info=exc)
        return JSONResponse(
            {"error": "Service temporarily unavailable"}, status_code=503
        )
    log_event(user, "block_ip", {"ip": normalized_ip})
    return JSONResponse({"status": "success", "ip": normalized_ip})


@router.post("/unblock")
async def unblock_ip(request: Request, user: str = Depends(require_admin)):
    json_data = await read_json_body(request)
    if not json_data:
        return JSONResponse(
            {"error": "Invalid request, missing JSON body"}, status_code=400
        )

    ip = json_data.get("ip")
    if not ip:
        return JSONResponse({"error": "Invalid request, missing ip"}, status_code=400)
    try:
        normalized_ip = str(ipaddress.ip_address(ip))
    except ValueError:
        return JSONResponse({"error": "Invalid ip"}, status_code=400)

    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)

    try:
        redis_conn.srem(tenant_key("blocklist"), normalized_ip)
    except RedisError as exc:
        logger.error("Error removing IP from blocklist", exc_info=exc)
        return JSONResponse(
            {"error": "Service temporarily unavailable"}, status_code=503
        )
    log_event(user, "unblock_ip", {"ip": normalized_ip})
    return JSONResponse({"status": "success", "ip": normalized_ip})
