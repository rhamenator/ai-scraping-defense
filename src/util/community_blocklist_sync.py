import asyncio
import ipaddress
import json
import logging
import os
from typing import List, Optional

import httpx

from src.shared.config import tenant_key
from src.shared.operational_events import publish_operational_event
from src.shared.redis_client import get_redis_connection

COMMUNITY_BLOCKLIST_API_URL = os.getenv(
    "COMMUNITY_BLOCKLIST_API_URL", "https://mock_community_blocklist_api:8000"
)
COMMUNITY_BLOCKLIST_LIST_ENDPOINT = os.getenv(
    "COMMUNITY_BLOCKLIST_LIST_ENDPOINT", "/list"
)
REDIS_DB_BLOCKLIST = int(os.getenv("REDIS_DB_BLOCKLIST", 2))
BLOCKLIST_TTL_SECONDS = int(os.getenv("COMMUNITY_BLOCKLIST_TTL_SECONDS", 86400))

logger = logging.getLogger(__name__)


async def fetch_blocklist(url: str) -> List[str]:
    """Fetch a list of malicious IPs from the community blocklist service."""
    if not url.startswith(("http://", "https://")):
        logger.warning("Skipping invalid URL: %s", url)
        return []
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            logger.error("Failed to decode JSON from %s: %s", url, exc)
            return []
        if isinstance(data, list):
            return [ip for ip in data if isinstance(ip, str)]
        if isinstance(data, dict):
            ips = data.get("ips")
            if isinstance(ips, list):
                return [ip for ip in ips if isinstance(ip, str)]
        return []


def update_redis_blocklist(ips: List[str], redis_conn) -> int:
    """Adds IPs to the Redis blocklist with a TTL."""
    if not redis_conn or not ips:
        return 0
    added = 0
    for ip in ips:
        try:
            parsed_ip = ipaddress.ip_address(ip)
        except ValueError:
            logger.warning("Skipping invalid IP address: %s", ip)
            continue
        key = tenant_key(f"blocklist:ip:{parsed_ip}")
        try:
            redis_conn.setex(key, BLOCKLIST_TTL_SECONDS, "community")
            added += 1
        except Exception as e:  # pragma: no cover - unexpected redis error
            logger.error(f"Failed to set Redis key for IP {parsed_ip}: {e}")
    return added


async def sync_blocklist() -> Optional[int]:
    """Fetches the community blocklist and updates Redis."""
    list_url = (
        COMMUNITY_BLOCKLIST_API_URL.rstrip("/") + COMMUNITY_BLOCKLIST_LIST_ENDPOINT
    )
    logger.info(f"Fetching community blocklist from {list_url}")
    try:
        ips = await fetch_blocklist(list_url)
    except Exception as e:
        logger.error(f"Failed to fetch community blocklist: {e}")
        publish_operational_event(
            "blocklist_sync_failed",
            {"source": "community", "error": str(e), "url": list_url},
        )
        return None
    if not ips:
        logger.info("No IPs retrieved from community blocklist.")
        publish_operational_event(
            "blocklist_sync_empty", {"source": "community", "url": list_url}
        )
        return 0
    redis_conn = get_redis_connection(db_number=REDIS_DB_BLOCKLIST)
    if not redis_conn:
        logger.error("Could not connect to Redis for blocklist updates.")
        publish_operational_event(
            "blocklist_sync_failed",
            {"source": "community", "error": "redis_unavailable"},
        )
        return None
    added = update_redis_blocklist(ips, redis_conn)
    logger.info(f"Added/updated {added} IPs from community blocklist.")
    publish_operational_event(
        "blocklist_sync_completed",
        {"source": "community", "added": added, "total": len(ips), "url": list_url},
    )
    return added


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    asyncio.run(sync_blocklist())
