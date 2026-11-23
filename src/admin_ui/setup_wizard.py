"""Authenticated first-run Setup Wizard state and helpers for the Admin UI."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from redis.exceptions import RedisError

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

_FALLBACK_SETUP_STATE: dict[str, Any] = {}


def _setup_state_key() -> str:
    return tenant_key("admin_ui:setup:state")


def get_setup_state() -> dict[str, Any]:
    """Return persisted onboarding status from Redis or in-memory fallback."""
    redis_conn = get_redis_connection()
    if not redis_conn:
        return dict(_FALLBACK_SETUP_STATE)
    try:
        raw = redis_conn.get(_setup_state_key())
        if raw:
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            if isinstance(data, dict):
                return data
    except (RedisError, json.JSONDecodeError):
        pass
    return dict(_FALLBACK_SETUP_STATE)


def is_setup_complete() -> bool:
    """Return True once the authenticated /setup wizard has been completed or skipped."""
    if os.getenv("ADMIN_UI_SKIP_SETUP_WIZARD", "false").strip().lower() == "true":
        return True
    state = get_setup_state()
    if "completed" in state:
        return bool(state["completed"])
    return False


def mark_setup_complete(user: str, completed: bool = True) -> dict[str, Any]:
    """Persist setup wizard completion state in Redis and fallback memory."""
    payload = {
        "completed": completed,
        "completed_by": user,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    _FALLBACK_SETUP_STATE.clear()
    _FALLBACK_SETUP_STATE.update(payload)
    redis_conn = get_redis_connection()
    if redis_conn:
        try:
            redis_conn.set(_setup_state_key(), json.dumps(payload))
        except RedisError:
            pass
    return payload
