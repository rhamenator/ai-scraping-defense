import asyncio
import datetime
import hmac
import ipaddress
import json
import logging
import os
from collections import deque

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from src.shared import blocklist_store
from src.shared.audit import log_event
from src.shared.config import CONFIG
from src.shared.redis_client import get_redis_connection
from src.shared.request_identity import is_trusted_infrastructure_ip
from src.shared.request_utils import read_json_body

from . import metrics
from .auth import require_admin, require_auth

logger = logging.getLogger(__name__)

BLOCK_LOG_FILE = os.getenv("BLOCK_LOG_FILE", "/app/logs/block_events.log")

router = APIRouter()

MAX_BLOCK_REASON_LENGTH = 200


def _require_csrf(request: Request) -> None:
    """Reject state-changing calls that do not echo the CSRF cookie in X-CSRF-Token.

    The admin API accepts Basic credentials, which browsers resend on cross-site requests, so
    block and unblock must prove the request came from a page this server rendered (#1950).
    """
    cookie = request.cookies.get("csrf_token")
    header = request.headers.get("X-CSRF-Token")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def _clean_reason(value) -> str | None:
    """Return a bounded single-line reason, or None when none was supplied."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="reason must be text")
    reason = " ".join(value.split())
    if len(reason) > MAX_BLOCK_REASON_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"reason must be at most {MAX_BLOCK_REASON_LENGTH} characters",
        )
    return reason or None


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


_legacy_migrated = False


def _blocklist_connection():
    """The blocklist database, the one the edge reads (#1902).

    The first time it is used, blocks that earlier releases stored where the edge never looked are moved to the real
    key (the admin UI used a set in the default database).
    """
    global _legacy_migrated
    conn = get_redis_connection(db_number=CONFIG.REDIS_DB_BLOCKLIST)
    if conn and not _legacy_migrated:
        _legacy_migrated = True
        try:
            blocklist_store.migrate_legacy(conn=conn, extra_conns=(get_redis_connection(),))
        except Exception as exc:  # noqa: BLE001 - migration must never break the admin UI
            logger.error("Legacy blocklist migration failed: %s", exc)
    return conn


def _bot_human_totals() -> tuple[float, float]:
    try:
        metrics_dict = metrics._get_metrics_dict_func()
    except Exception as exc:
        logger.error("Failed to load metrics", exc_info=exc)
        metrics_dict = {}
    bots = sum(float(v) for k, v in metrics_dict.items() if k.startswith("bots_detected"))
    humans = sum(float(v) for k, v in metrics_dict.items() if k.startswith("humans_detected"))
    return bots, humans


@router.get("/block_stats")
async def block_stats(user: str = Depends(require_auth)):
    """Return blocklist counts and bot detection statistics."""
    total_bots, total_humans = _bot_human_totals()

    redis_conn = _blocklist_connection()
    blocked_ip_count = 0
    temp_block_count = 0
    if redis_conn:
        try:
            totals = blocklist_store.counts(redis_conn)
            blocked_ip_count, temp_block_count = totals["blocked"], totals["temporary"]
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
            "blocked_ip_count": blocked_ip_count,
            "temporary_block_count": temp_block_count,
            "total_bots_detected": total_bots,
            "total_humans_detected": total_humans,
            "recent_block_events": recent_events,
        }
    )


@router.get("/blocklist")
async def get_blocklist(user: str = Depends(require_auth)):
    redis_conn = _blocklist_connection()
    if not redis_conn:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)

    try:
        return JSONResponse(blocklist_store.list_blocked(redis_conn))
    except RedisError as exc:
        logger.error("Error retrieving blocklist", exc_info=exc)
        return JSONResponse(
            {"error": "Service temporarily unavailable"}, status_code=503
        )


def _block_request(json_data) -> tuple[str | None, str, JSONResponse | None]:
    """The address and reason of a block request, or the error response to send instead."""
    ip = json_data.get("ip")
    if not ip:
        return None, "", JSONResponse({"error": "Invalid request, missing ip"}, status_code=400)
    try:
        normalized_ip = str(ipaddress.ip_address(ip))
    except ValueError:
        return None, "", JSONResponse({"error": "Invalid ip"}, status_code=400)
    if is_trusted_infrastructure_ip(normalized_ip):
        return None, "", JSONResponse(
            {"error": "Refusing to block a configured proxy or CDN address"},
            status_code=400,
        )
    return normalized_ip, _clean_reason(json_data.get("reason")), None


@router.post("/block")
async def block_ip(request: Request, user: str = Depends(require_admin)):
    _require_csrf(request)
    json_data = await read_json_body(request)
    if not json_data:
        return JSONResponse(
            {"error": "Invalid request, missing JSON body"}, status_code=400
        )

    normalized_ip, reason, error = _block_request(json_data)
    if error is not None:
        return error

    redis_conn = _blocklist_connection()
    if not redis_conn:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)

    # An administrator's block stays until it is lifted; the edge reads this key (#1902).
    if not blocklist_store.block(
        normalized_ip, reason or "blocked by administrator", source="admin_ui", conn=redis_conn
    ):
        return JSONResponse(
            {"error": "Service temporarily unavailable"}, status_code=503
        )
    details = {"ip": normalized_ip}
    if reason:
        details["reason"] = reason
    log_event(user, "block_ip", details)
    return JSONResponse({"status": "success", "ip": normalized_ip})


@router.post("/unblock")
async def unblock_ip(request: Request, user: str = Depends(require_admin)):
    _require_csrf(request)
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

    redis_conn = _blocklist_connection()
    if not redis_conn:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)

    if not blocklist_store.unblock(
        normalized_ip, conn=redis_conn, legacy_conns=(get_redis_connection(),)
    ):
        return JSONResponse(
            {"error": "Service temporarily unavailable"}, status_code=503
        )
    log_event(user, "unblock_ip", {"ip": normalized_ip})
    return JSONResponse({"status": "success", "ip": normalized_ip})
