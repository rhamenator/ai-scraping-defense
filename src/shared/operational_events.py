"""Lightweight operational event publisher for alert and blocklist workflows."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.shared.metrics import OPERATIONAL_EVENTS
from src.shared.redis_client import get_redis_connection

logger = logging.getLogger(__name__)


def _events_enabled() -> bool:
    return os.getenv("OPERATIONAL_EVENT_STREAM_ENABLED", "false").lower() == "true"


def _event_channel() -> str:
    return os.getenv("OPERATIONAL_EVENT_CHANNEL", "operational_events")


def _event_db() -> int:
    return int(os.getenv("OPERATIONAL_EVENT_REDIS_DB", "0"))


def publish_operational_event(
    event_type: str, payload: Dict[str, Any]
) -> Optional[str]:
    """Publish an operational event to Redis when enabled."""
    OPERATIONAL_EVENTS.labels(event_type=event_type).inc()
    if not _events_enabled():
        return None

    redis_conn = get_redis_connection(db_number=_event_db())
    if not redis_conn:
        logger.warning("Operational event publish skipped: Redis unavailable.")
        return None

    event = {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    try:
        return redis_conn.publish(_event_channel(), json.dumps(event, default=str))
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to publish operational event: %s", exc)
        return None
