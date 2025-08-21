import asyncio
import json
import logging
import os
from typing import Dict

import httpx

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
    if (
        "scraping" in reason.lower()
        or "crawler" in reason.lower()
        or "llm" in reason.lower()
    ):
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
