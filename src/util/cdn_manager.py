import logging
import os

import httpx

from src.shared.config import get_secret

logger = logging.getLogger(__name__)


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _cloudflare_purge_url() -> str | None:
    explicit_url = (os.getenv("CDN_PURGE_URL") or "").strip()
    if explicit_url:
        return explicit_url
    zone_id = (os.getenv("CLOUD_CDN_ZONE_ID") or "").strip()
    if not zone_id:
        return None
    return f"https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache"


async def purge_cache() -> bool:
    """Request a cache purge from the CDN provider if enabled."""
    if not _is_truthy(os.getenv("ENABLE_GLOBAL_CDN")):
        logger.debug("CDN integration disabled.")
        return False

    provider = (os.getenv("CLOUD_CDN_PROVIDER") or "cloudflare").strip().lower()
    if provider != "cloudflare":
        logger.warning("Unsupported CDN provider '%s'. Skipping cache purge.", provider)
        return False

    api_token = os.getenv("CLOUD_CDN_API_TOKEN") or get_secret(
        "CLOUD_CDN_API_TOKEN_FILE"
    )
    if not api_token:
        logger.debug("CDN integration disabled or API token unavailable.")
        return False

    api_url = _cloudflare_purge_url()
    if not api_url:
        logger.warning(
            "Missing Cloudflare zone configuration; set CLOUD_CDN_ZONE_ID or CDN_PURGE_URL."
        )
        return False

    headers = {"Authorization": f"Bearer {api_token}"}
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


if __name__ == "__main__":  # pragma: no cover - manual execution
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
