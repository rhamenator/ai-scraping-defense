import os
import logging
import httpx
from src.shared.config import get_secret

ENABLE_GLOBAL_CDN = os.getenv("ENABLE_GLOBAL_CDN", "false").lower() == "true"
CLOUD_CDN_PROVIDER = os.getenv("CLOUD_CDN_PROVIDER", "genericcdn")
CLOUD_CDN_API_TOKEN = os.getenv("CLOUD_CDN_API_TOKEN") or get_secret(
    "CLOUD_CDN_API_TOKEN_FILE"
)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def purge_cache() -> bool:
    """Request a cache purge from the CDN provider if enabled."""
    if not ENABLE_GLOBAL_CDN or not CLOUD_CDN_API_TOKEN:
        logger.debug("CDN integration disabled or API token unavailable.")
        return False
    api_url = os.getenv(
        "CDN_PURGE_URL", "https://api.genericcdn.com/client/v4/zones/purge_cache"
    )
    headers = {"Authorization": f"Bearer {CLOUD_CDN_API_TOKEN}"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                api_url, headers=headers, json={"purge_everything": True}, timeout=10.0
            )
            resp.raise_for_status()
        logger.info("CDN cache purge requested.")
        return True
    except Exception as e:  # pragma: no cover - network/HTTP errors
        logger.error(f"Failed to purge CDN cache: {e}")
        return False
