import datetime
import logging
import os
from typing import Any, Dict, Optional

import httpx

from src.shared.config import CONFIG, get_secret

ENABLE_DDOS_PROTECTION = os.getenv("ENABLE_DDOS_PROTECTION", "true").lower() == "true"
DDOS_PROTECTION_PROVIDER_URL = os.getenv("DDOS_PROTECTION_PROVIDER_URL")
DDOS_PROTECTION_API_KEY = os.getenv("DDOS_PROTECTION_API_KEY") or get_secret(
    "DDOS_PROTECTION_API_KEY_FILE"
)
DDOS_INTERNAL_ENDPOINT = os.getenv("DDOS_INTERNAL_ENDPOINT", CONFIG.ESCALATION_ENDPOINT)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def report_attack(
    ip: str,
    metadata: Optional[Dict[str, Any]] = None,
    attack_type: str = "unspecified",
) -> bool:
    """Submit a suspected attack IP for analysis.

    If an external provider URL and API key are configured, the event is
    reported there. Otherwise the request metadata is sent to the local
    escalation engine at ``CONFIG.ESCALATION_ENDPOINT``. The
    ``DDOS_INTERNAL_ENDPOINT`` variable may override this default but is not
    prompted for during setup.
    """

    if not ENABLE_DDOS_PROTECTION:
        logger.debug("DDoS protection disabled.")
        return False

    if DDOS_PROTECTION_PROVIDER_URL and DDOS_PROTECTION_API_KEY:
        if not DDOS_PROTECTION_PROVIDER_URL.startswith("https://"):
            logger.error(
                "DDOS_PROTECTION_PROVIDER_URL must start with 'https://'; "
                "skipping external reporting"
            )
        else:
            headers = {"Authorization": f"Bearer {DDOS_PROTECTION_API_KEY}"}
            payload = {"ip": ip}
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        DDOS_PROTECTION_PROVIDER_URL,
                        headers=headers,
                        json=payload,
                        timeout=10.0,
                    )
                    resp.raise_for_status()
                logger.info(f"Reported IP {ip} to external DDoS provider.")
                return True
            except Exception as e:  # pragma: no cover - network/HTTP errors
                logger.error(f"Failed to report IP {ip} to DDoS provider: {e}")
                return False

    # Fall back to local escalation engine
    if metadata is None:
        metadata = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "ip": ip,
            "source": "ddos_guard",
        }
    metadata.setdefault("attack_type", attack_type)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                DDOS_INTERNAL_ENDPOINT, json=metadata, timeout=10.0
            )
            resp.raise_for_status()
        logger.info(f"Submitted IP {ip} to internal DDoS analysis.")
        return True
    except Exception as e:  # pragma: no cover - network/HTTP errors
        logger.error(f"Failed to submit IP {ip} for internal analysis: {e}")
        return False
