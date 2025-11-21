import datetime
import logging
import os
from typing import Any, Dict, Optional

import httpx

from src.shared.config import CONFIG, get_secret

try:
    from src.security.mobile_security import MobileThreatDetector
except ImportError:  # pragma: no cover - optional dependency
    MobileThreatDetector = None  # type: ignore

ENABLE_DDOS_PROTECTION = os.getenv("ENABLE_DDOS_PROTECTION", "true").lower() == "true"
DDOS_PROTECTION_PROVIDER_URL = os.getenv("DDOS_PROTECTION_PROVIDER_URL")
DDOS_PROTECTION_API_KEY = os.getenv("DDOS_PROTECTION_API_KEY") or get_secret(
    "DDOS_PROTECTION_API_KEY_FILE"
)
DDOS_INTERNAL_ENDPOINT = os.getenv("DDOS_INTERNAL_ENDPOINT", CONFIG.ESCALATION_ENDPOINT)

logger = logging.getLogger(__name__)


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

    Args:
        ip: The IP address to report
        metadata: Additional metadata about the attack
        attack_type: Type of attack (e.g., "mobile_botnet", "ddos", "unspecified")
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
            try:
                # Build request and send to external provider
                headers = {"Authorization": f"Bearer {DDOS_PROTECTION_API_KEY}"}
                payload = {"ip": ip, "attack_type": attack_type}
                if metadata:
                    payload["metadata"] = metadata
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
            "timestamp": datetime.datetime.now(datetime.UTC)
            .isoformat()
            .replace("+00:00", "Z"),
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


def detect_mobile_botnet_pattern(
    user_agent: str, request_count: int, time_window: int = 60
) -> bool:
    """Detect if traffic pattern suggests mobile botnet activity.

    Args:
        user_agent: User-Agent header
        request_count: Number of requests in time window
        time_window: Time window in seconds

    Returns:
        True if mobile botnet pattern detected
    """
    if not user_agent or not MobileThreatDetector:
        return False

    # High request rate from mobile device is suspicious
    requests_per_second = request_count / time_window
    if requests_per_second > 2.0:  # More than 2 req/sec from mobile
        # Check if it's a mobile user agent
        ua_lower = user_agent.lower()
        is_mobile = any(
            x in ua_lower for x in ["iphone", "ipad", "android", "mobile"]
        )
        if is_mobile:
            logger.warning(
                f"Possible mobile botnet: {requests_per_second:.2f} req/s "
                f"from mobile UA: {user_agent[:50]}"
            )
            return True

    return False


if __name__ == "__main__":  # pragma: no cover - manual execution
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
