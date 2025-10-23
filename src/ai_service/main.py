import asyncio
import hashlib
import hmac
import ipaddress
import logging
import os
import time
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from redis.exceptions import RedisError

from src.shared.audit import log_event as audit_log_event
from src.shared.config import CONFIG, Config, tenant_key
from src.shared.middleware import create_app
from src.shared.observability import (
    HealthCheckResult,
    register_health_check,
    trace_span,
)
from src.shared.redis_client import get_redis_connection
from src.shared.request_utils import read_json_body

logger = logging.getLogger(__name__)

LOG_DIR = "/app/logs"
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except OSError as e:  # pragma: no cover
    logger.error("Cannot create log directory %s: %s", LOG_DIR, e)

_request_counts: dict[str, tuple[int, float]] = {}
_rate_lock = asyncio.Lock()


class WebhookEvent(BaseModel):
    event_type: str = Field(
        ..., description="Type of event, e.g., 'suspicious_activity_detected'"
    )
    reason: str = Field(
        ...,
        description="Reason for the event/block, e.g., 'High Combined Score (0.95)'",
    )
    timestamp_utc: Any = Field(..., description="Timestamp of the original detection")
    details: Dict[str, Any] = Field(
        ..., description="Detailed metadata about the request (IP, UA, headers, etc.)"
    )


class WebhookAction(BaseModel):
    action: str
    ip: Optional[str] = None
    reason: Optional[str] = Field(None, max_length=256)


app = create_app()


@register_health_check(app, "redis", critical=True)
async def _redis_health() -> HealthCheckResult:
    redis_conn = get_redis_connection(db_number=CONFIG.REDIS_DB_BLOCKLIST)
    if not redis_conn:
        return HealthCheckResult.degraded({"reason": "redis connection unavailable"})
    try:
        if hasattr(redis_conn, "ping"):
            redis_conn.ping()
    except RedisError as exc:  # pragma: no cover - network interaction
        return HealthCheckResult.unhealthy({"error": str(exc)})
    return HealthCheckResult.healthy()


def get_config() -> Config:
    return CONFIG


def get_redis_blocklist(config: Config = Depends(get_config)):
    return get_redis_connection(db_number=config.REDIS_DB_BLOCKLIST)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def get_client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def calculate_window_reset(now: float, window: int) -> int:
    current_window_start = (now // window) * window
    next_window_start = current_window_start + window
    return int(next_window_start)


async def _cleanup_expired_requests(now: float) -> None:
    async with _rate_lock:
        expired = [ip for ip, (_, reset) in _request_counts.items() if now > reset]
        for ip in expired:
            del _request_counts[ip]


# ---------------------------------------------------------------------------
# FastAPI endpoints
# ---------------------------------------------------------------------------


@app.post("/webhook")
async def webhook_receiver(
    request: Request,
    response: Response,
    config: Config = Depends(get_config),
    redis_conn=Depends(get_redis_blocklist),
):
    """Handle blocklist/flag actions from the escalation engine tests."""
    if not config.WEBHOOK_SHARED_SECRET:
        raise HTTPException(status_code=500, detail="Shared secret not configured")
    client_ip = get_client_ip(request)
    with trace_span("ai_service.read_payload"):
        payload = await read_json_body(request)
    # Validate payload schema
    try:
        action_req = WebhookAction.model_validate(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload schema")
    body_bytes = request.state.body_bytes
    signature = request.headers.get("X-Signature", "")
    expected = hmac.new(
        config.WEBHOOK_SHARED_SECRET.encode("utf-8"), body_bytes, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        audit_log_event(client_ip, "webhook_auth_failed", {"ip": client_ip})
        raise HTTPException(status_code=401, detail="Unauthorized")

    now = time.time()
    window_reset = calculate_window_reset(now, config.WEBHOOK_RATE_LIMIT_WINDOW)
    await _cleanup_expired_requests(now)
    async with _rate_lock:
        count, reset = _request_counts.get(client_ip, (0, window_reset))
        if now > reset:
            count, reset = 0, window_reset
        new_count = count + 1
        if new_count > config.WEBHOOK_RATE_LIMIT_REQUESTS:
            retry_after = int(reset - now)
            headers = {
                "X-RateLimit-Limit": str(config.WEBHOOK_RATE_LIMIT_REQUESTS),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(reset)),
                "Retry-After": str(retry_after),
            }
            audit_log_event(client_ip, "webhook_rate_limited", {"ip": client_ip})
            raise HTTPException(
                status_code=429, detail="Too Many Requests", headers=headers
            )
        _request_counts[client_ip] = (new_count, reset)
        remaining = config.WEBHOOK_RATE_LIMIT_REQUESTS - new_count

    response.headers["X-RateLimit-Limit"] = str(config.WEBHOOK_RATE_LIMIT_REQUESTS)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(int(reset))

    if not redis_conn:
        audit_log_event(client_ip, "webhook_redis_unavailable", {"ip": client_ip})
        raise HTTPException(status_code=503, detail="Redis service unavailable")

    action = action_req.action
    ip = str(action_req.ip) if action_req.ip is not None else None

    actions_requiring_ip = {"block_ip", "allow_ip", "flag_ip", "unflag_ip"}
    if action in actions_requiring_ip:
        if not ip:
            raise HTTPException(
                status_code=400,
                detail=f"Missing 'ip' in payload for action '{action}'.",
            )
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid IP address: {ip}")

    try:
        with trace_span("ai_service.execute_action", attributes={"action": action, "ip": ip}):
            if action == "block_ip":
                redis_conn.sadd(tenant_key("blocklist"), ip)
                audit_log_event(client_ip, "webhook_block_ip", {"ip": ip})
                return {"status": "success", "message": f"IP {ip} added to blocklist."}
            elif action == "allow_ip":
                redis_conn.srem(tenant_key("blocklist"), ip)
                audit_log_event(client_ip, "webhook_allow_ip", {"ip": ip})
                return {
                    "status": "success",
                    "message": f"IP {ip} removed from blocklist.",
                }
            elif action == "flag_ip":
                reason = action_req.reason or ""
                redis_conn.set(tenant_key(f"ip_flag:{ip}"), reason)
                audit_log_event(client_ip, "webhook_flag_ip", {"ip": ip})
                return {"status": "success", "message": f"IP {ip} flagged."}
            elif action == "unflag_ip":
                redis_conn.delete(tenant_key(f"ip_flag:{ip}"))
                audit_log_event(client_ip, "webhook_unflag_ip", {"ip": ip})
                return {"status": "success", "message": f"IP {ip} unflagged."}
            else:
                raise HTTPException(status_code=400, detail=f"Invalid action: {action}")
    except HTTPException:
        raise
    except RedisError as e:
        logger.error("Redis error during action %s: %s", action, e)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    except Exception as e:
        logger.error("Failed to execute action: %s", e)
        raise HTTPException(status_code=500, detail="Failed to execute action")


if __name__ == "__main__":  # pragma: no cover - manual run
    import uvicorn

    port = CONFIG.AI_SERVICE_PORT
    workers = int(os.getenv("UVICORN_WORKERS", 2))
    log_level = CONFIG.LOG_LEVEL.lower()
    logger.info("--- AI Service / Webhook Receiver Starting ---")
    uvicorn.run(
        "src.ai_service.main:app",
        host=os.getenv("WEBHOOK_HOST", "127.0.0.1"),
        port=port,
        workers=workers,
        log_level=log_level,
        reload=False,
    )
    logger.info("--- AI Service / Webhook Receiver Started ---")
