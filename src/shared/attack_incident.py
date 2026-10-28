"""Aggregate suspicious requests and alert operators about an active incident."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

import httpx
from redis.exceptions import RedisError

from src.shared.config import tenant_key
from src.shared.operational_events import publish_operational_event
from src.shared.redis_client import get_redis_connection

logger = logging.getLogger(__name__)


def _positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        logger.warning("Invalid %s; using %s", name, default)
        return default


def _record_signal(ip: str) -> tuple[int, int] | None:
    """Count one suspicious request and its source in the current time window."""
    window = _positive_int("ATTACK_INCIDENT_WINDOW_SECONDS", 300)
    bucket = int(time.time() // window)
    redis_conn = get_redis_connection(db_number=0)
    if redis_conn is None:
        logger.warning("Attack incident signal skipped: Redis unavailable")
        return None

    count_key = tenant_key(f"attack_incident:count:{bucket}")
    sources_key = tenant_key(f"attack_incident:sources:{bucket}")
    try:
        pipe = redis_conn.pipeline()
        pipe.incr(count_key)
        pipe.sadd(sources_key, ip)
        pipe.expire(count_key, window * 2)
        pipe.expire(sources_key, window * 2)
        count = int(pipe.execute()[0])
        return count, int(redis_conn.scard(sources_key))
    except RedisError as exc:
        logger.warning("Attack incident signal could not be recorded: %s", exc)
        return None


def _claim_alert() -> bool:
    redis_conn = get_redis_connection(db_number=0)
    if redis_conn is None:
        return False
    cooldown = _positive_int("ATTACK_INCIDENT_COOLDOWN_SECONDS", 900)
    try:
        return bool(
            redis_conn.set(
                tenant_key("attack_incident:alert_cooldown"),
                "1",
                nx=True,
                ex=cooldown,
            )
        )
    except RedisError as exc:
        logger.warning("Attack incident alert could not be claimed: %s", exc)
        return False


async def _origin_health(url: str | None) -> str:
    if not url:
        return "unconfigured"
    if not url.startswith(("http://", "https://")):
        logger.warning("Origin health URL must use HTTP or HTTPS")
        return "unconfigured"
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
            response = await client.get(url, follow_redirects=False)
        return "healthy" if response.status_code < 400 else "unhealthy"
    except httpx.RequestError:
        return "unhealthy"


async def record_and_alert_attack(ip: str, score: float, source: str) -> None:
    """Send one actionable advisory when recent suspicious traffic crosses a threshold.

    This function never changes Cloudflare settings or switches origins.
    """
    if os.getenv("ALERT_METHOD", "none").strip().lower() not in {
        "webhook",
        "slack",
        "smtp",
    }:
        return
    signal = await asyncio.to_thread(_record_signal, ip)
    if signal is None:
        return
    count, unique_sources = signal
    min_events = _positive_int("ATTACK_INCIDENT_MIN_EVENTS", 25)
    min_sources = _positive_int("ATTACK_INCIDENT_MIN_UNIQUE_IPS", 5)
    if count < min_events or unique_sources < min_sources:
        return
    if not await asyncio.to_thread(_claim_alert):
        return

    primary, backup = await asyncio.gather(
        _origin_health(os.getenv("ATTACK_INCIDENT_PRIMARY_HEALTH_URL")),
        _origin_health(os.getenv("ATTACK_INCIDENT_BACKUP_HEALTH_URL")),
    )
    recommendations: list[str] = []
    if (
        os.getenv("ENABLE_GLOBAL_CDN", "false").lower() in {"1", "true", "yes", "on"}
        and os.getenv("CLOUD_CDN_PROVIDER", "cloudflare").lower() == "cloudflare"
    ):
        recommendations.append("review_cloudflare_under_attack_mode")
    if primary == "unhealthy" and backup == "healthy":
        recommendations.append("review_failover_to_healthy_backup")

    window = _positive_int("ATTACK_INCIDENT_WINDOW_SECONDS", 300)
    details = {
        "ip": ip,
        "source": source,
        "score": round(score, 3),
        "suspicious_requests": count,
        "unique_client_ips": unique_sources,
        "window_seconds": window,
        "primary_health": primary,
        "backup_health": backup,
        "recommended_actions": recommendations,
        "operator_action_required": True,
    }
    publish_operational_event("attack_incident_detected", details)

    from src.ai_service.alerts import send_alert
    from src.ai_service.main import WebhookEvent

    action_text = ", ".join(recommendations) or "review_origin_and_edge_mitigation"
    event = WebhookEvent(
        event_type="attack_incident",
        reason=f"Attack Incident ({count} requests, {unique_sources} IPs; {action_text})",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        details=details,
    )
    await send_alert(event)
