import asyncio
import json
import logging
import os
from typing import Dict

import httpx
import redis.asyncio as redis

from src.shared.config import CONFIG
from src.shared.utils import LOG_DIR, log_event

from .metrics_ai_service import (
    COMMUNITY_REPORTS_ATTEMPTED,
    COMMUNITY_REPORTS_ERRORS_REQUEST,
    COMMUNITY_REPORTS_ERRORS_RESPONSE_DECODE,
    COMMUNITY_REPORTS_ERRORS_STATUS,
    COMMUNITY_REPORTS_ERRORS_TIMEOUT,
    COMMUNITY_REPORTS_ERRORS_UNEXPECTED,
    COMMUNITY_REPORTS_SUCCESS,
    increment_counter_metric,
)

logger = logging.getLogger(__name__)

ENABLE_COMMUNITY_REPORTING = CONFIG.ENABLE_COMMUNITY_REPORTING
COMMUNITY_BLOCKLIST_REPORT_URL = CONFIG.COMMUNITY_BLOCKLIST_REPORT_URL
COMMUNITY_BLOCKLIST_API_KEY = CONFIG.COMMUNITY_BLOCKLIST_API_KEY
COMMUNITY_BLOCKLIST_REPORT_TIMEOUT = CONFIG.COMMUNITY_BLOCKLIST_REPORT_TIMEOUT

COMMUNITY_REPORT_LOG_FILE = os.path.join(LOG_DIR, "community_report.log")

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")
REPORTING_EVENT_CHANNEL = "reporting_events"


async def report_ip_to_community(ip: str, reason: str, details: Dict) -> bool:
    if (
        not ENABLE_COMMUNITY_REPORTING
        or not COMMUNITY_BLOCKLIST_REPORT_URL
        or not COMMUNITY_BLOCKLIST_API_KEY
        or not ip
    ):
        if ENABLE_COMMUNITY_REPORTING and ip:
            logger.debug(
                "Community reporting skipped for IP %s: URL or API Key not configured.",
                ip,
            )
        return False

    # Apply GDPR data minimization before reporting
    try:
        from src.shared.gdpr import get_gdpr_manager
        gdpr = get_gdpr_manager()
        details = gdpr.minimize_data(details)
    except Exception as e:
        logger.warning(f"GDPR data minimization failed: {e}")

    increment_counter_metric(COMMUNITY_REPORTS_ATTEMPTED)
    logger.info(
        "Reporting IP %s to community blocklist: %s",
        ip,
        COMMUNITY_BLOCKLIST_REPORT_URL,
    )
    headers = {"Accept": "application/json", "Key": COMMUNITY_BLOCKLIST_API_KEY}
    categories = "18"  # Default: Brute-Force
    if "scan" in reason.lower():
        categories = "14"
    if "scraping" in reason.lower() or "crawler" in reason.lower() or "llm" in reason.lower():
        categories = "19"
    if "honeypot" in reason.lower():
        categories = "22"
    comment = (
        "AI Defense Stack Detection. Reason: "
        f"{reason}. UA: {details.get('user_agent', 'N/A')}. "
        f"Path: {details.get('path', 'N/A')}"
    )
    payload = {"ip": ip, "categories": categories, "comment": comment[:1024]}
    response = None
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                COMMUNITY_BLOCKLIST_REPORT_URL,
                headers=headers,
                data=payload,
                timeout=COMMUNITY_BLOCKLIST_REPORT_TIMEOUT,
            )
            response.raise_for_status()
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(response.json),
                    COMMUNITY_BLOCKLIST_REPORT_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Timeout parsing community blocklist report response for IP %s",
                    ip,
                )
                increment_counter_metric(COMMUNITY_REPORTS_ERRORS_TIMEOUT)
                return False
            logger.info(
                "Successfully reported IP %s to community blocklist. Response: %s",
                ip,
                result,
            )
            log_event(
                COMMUNITY_REPORT_LOG_FILE,
                "COMMUNITY_REPORT_SUCCESS",
                {"ip": ip, "reason": reason, "api_response": result},
            )
            increment_counter_metric(COMMUNITY_REPORTS_SUCCESS)
            return True
    except httpx.TimeoutException:
        logger.error("Timeout reporting IP %s", ip)
        increment_counter_metric(COMMUNITY_REPORTS_ERRORS_TIMEOUT)
        return False
    except httpx.RequestError as exc:
        logger.error("Request error reporting IP %s: %s", ip, exc)
        increment_counter_metric(COMMUNITY_REPORTS_ERRORS_REQUEST)
        return False
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Community blocklist report failed for IP %s status %s. Response: %s",
            ip,
            exc.response.status_code,
            exc.response.text[:500],
        )
        increment_counter_metric(COMMUNITY_REPORTS_ERRORS_STATUS)
        return False
    except json.JSONDecodeError as exc:
        logger.error(
            "JSON decode error for IP %s: %s - Response: %s",
            ip,
            exc,
            (response.text[:500] if response else "No response"),
        )
        increment_counter_metric(COMMUNITY_REPORTS_ERRORS_RESPONSE_DECODE)
        return False
    except Exception as e:  # pragma: no cover - unexpected
        logger.error("Unexpected error reporting IP %s: %s", ip, e)
        increment_counter_metric(COMMUNITY_REPORTS_ERRORS_UNEXPECTED)
        return False


# ---------------------------------------------------------------------------
# Redis Event-Driven Operations
# ---------------------------------------------------------------------------


async def get_redis_client():
    """Create and return an async Redis client."""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True,
    )


async def subscribe_reporting_events():
    """Subscribe to reporting events from Redis Pub/Sub."""
    redis_client = await get_redis_client()
    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(REPORTING_EVENT_CHANNEL)
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    event_data = json.loads(message["data"])
                    await handle_reporting_event(event_data)
                except json.JSONDecodeError as e:
                    logger.error("Failed to decode reporting event: %s", e)
                except Exception as e:
                    logger.error("Error handling reporting event: %s", e)
    finally:
        await redis_client.aclose()


async def handle_reporting_event(event_data):
    """Process the reporting event."""
    ip = event_data.get("ip")
    reason = event_data.get("reason")
    details = event_data.get("details")
    if ip and reason and details:
        await report_ip_to_community(ip, reason, details)
    else:
        logger.warning("Invalid reporting event: %s", event_data)


async def main():
    """Main entry point for the Redis subscriber."""
    # Await the Redis subscriber task to keep the event loop running
    await subscribe_reporting_events()


if __name__ == "__main__":
    asyncio.run(main())
