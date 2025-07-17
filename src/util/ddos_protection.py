import os
import logging
import httpx
from src.shared.config import get_secret

ENABLE_DDOS_PROTECTION = os.getenv("ENABLE_DDOS_PROTECTION", "false").lower() == "true"
DDOS_PROTECTION_PROVIDER_URL = os.getenv("DDOS_PROTECTION_PROVIDER_URL")
DDOS_PROTECTION_API_KEY = os.getenv("DDOS_PROTECTION_API_KEY") or get_secret("DDOS_PROTECTION_API_KEY_FILE")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def report_attack(ip: str) -> bool:
    """Report a suspected attack IP to the DDoS protection service."""
    if not ENABLE_DDOS_PROTECTION or not DDOS_PROTECTION_PROVIDER_URL or not DDOS_PROTECTION_API_KEY:
        logger.debug("DDoS protection disabled or misconfigured.")
        return False
    headers = {"Authorization": f"Bearer {DDOS_PROTECTION_API_KEY}"}
    payload = {"ip": ip}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(DDOS_PROTECTION_PROVIDER_URL, headers=headers, json=payload, timeout=10.0)
            resp.raise_for_status()
        logger.info(f"Reported IP {ip} to DDoS provider.")
        return True
    except Exception as e:  # pragma: no cover - network/HTTP errors
        logger.error(f"Failed to report IP {ip} to DDoS provider: {e}")
        return False
