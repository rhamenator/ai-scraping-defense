import json
import logging
import os
from datetime import UTC, datetime
from typing import Any, Dict, List

import httpx

ESCALATION_URL = os.getenv(
    "ESCALATION_ENGINE_URL", "http://escalation_engine:8003/escalate"
)
EVE_LOG_PATH = os.getenv("SURICATA_EVE_LOG", "/var/log/suricata/eve.json")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_eve_alerts(path: str) -> List[Dict[str, Any]]:
    """Return alert events from a Suricata EVE JSON log."""
    alerts: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        logger.error("EVE log not found at %s", path)
        return alerts

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") == "alert":
                alerts.append(event)
    logger.info("Parsed %d alert events from %s", len(alerts), path)
    return alerts


def send_alert_to_escalation(event: Dict[str, Any]) -> bool:
    """Forward a Suricata alert to the escalation engine."""
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "ip": event.get("src_ip", "0.0.0.0"),
        "source": "suricata",
        "path": None,
        "method": None,
        "headers": None,
    }
    try:
        resp = httpx.post(ESCALATION_URL, json=payload, timeout=5.0)
        resp.raise_for_status()
        logger.info("Escalation sent for %s", payload["ip"])
        return True
    except Exception as exc:  # pragma: no cover - network errors
        logger.error("Failed to send escalation: %s", exc)
        return False


def process_eve_log() -> int:
    """Process the configured EVE log and send alerts to the escalation engine."""
    alerts = parse_eve_alerts(EVE_LOG_PATH)
    sent = 0
    for event in alerts:
        if send_alert_to_escalation(event):
            sent += 1
    logger.info("Processed %d alerts", sent)
    return sent


if __name__ == "__main__":
    process_eve_log()
