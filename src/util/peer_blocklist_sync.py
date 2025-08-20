import asyncio
import json
import logging
import os
from typing import List, Optional

import httpx

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

PEER_BLOCKLIST_URLS = os.getenv("PEER_BLOCKLIST_URLS", "")
REDIS_DB_BLOCKLIST = int(os.getenv("REDIS_DB_BLOCKLIST", 2))
PEER_BLOCKLIST_TTL_SECONDS = int(os.getenv("PEER_BLOCKLIST_TTL_SECONDS", 86400))

logger = logging.getLogger(__name__)


async def fetch_peer_ips(url: str) -> List[str]:
    """Fetch a list of malicious IPs from a peer deployment."""
    if not url.startswith(("http://", "https://")):
        logger.warning("Skipping invalid URL: %s", url)
        return []
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        try:
            data = resp.json()
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
    """Insert IPs into the Redis blocklist with a TTL."""
    if not ips or not redis_conn:
        return 0
    added = 0
    for ip in ips:
        key = tenant_key(f"blocklist:ip:{ip}")
        try:
            redis_conn.setex(key, PEER_BLOCKLIST_TTL_SECONDS, "peer")
            added += 1
        except Exception as exc:  # pragma: no cover - unexpected redis errors
            logger.error("Failed to set Redis key for IP %s: %s", ip, exc)
    return added


async def sync_peer_blocklists() -> Optional[int]:
    """Fetch blocklists from configured peers and update Redis."""
    if not PEER_BLOCKLIST_URLS:
        logger.info("No peer blocklist URLs configured.")
        return 0
    urls = [u.strip() for u in PEER_BLOCKLIST_URLS.split(",") if u.strip()]
    if not urls:
        logger.info("Peer blocklist URL list empty.")
        return 0
    redis_conn = get_redis_connection(db_number=REDIS_DB_BLOCKLIST)
    if not redis_conn:
        logger.error("Could not connect to Redis for peer blocklist updates.")
        return None
    total_added = 0
    for url in urls:
        if not url.startswith(("http://", "https://")):
            logger.warning("Skipping invalid URL: %s", url)
            continue
        try:
            logger.info("Fetching peer blocklist from %s", url)
            ips = await fetch_peer_ips(url)
        except Exception as e:  # pragma: no cover - network errors
            logger.error("Failed to fetch peer blocklist from %s: %s", url, e)
            continue
        added = update_redis_blocklist(ips, redis_conn)
        total_added += added
    logger.info("Added/updated %s IPs from peer blocklists.", total_added)
    return total_added


if __name__ == "__main__":  # pragma: no cover - manual execution
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    asyncio.run(sync_peer_blocklists())
