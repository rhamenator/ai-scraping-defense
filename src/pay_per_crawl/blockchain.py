"""Local hash-chained log for pay-per-crawl blockchain-style auditing."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

LOG_ENABLED = (
    os.getenv("PAY_PER_CRAWL_BLOCKCHAIN_LOG_ENABLED", "false").lower() == "true"
)
LOG_PATH = Path(
    os.getenv("PAY_PER_CRAWL_BLOCKCHAIN_LOG_PATH", "logs/pay_per_crawl_blockchain.log")
)

_last_hash: Optional[str] = None


def _load_last_hash() -> Optional[str]:
    if not LOG_PATH.exists():
        return None
    try:
        last_line = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()[-1]
        payload = json.loads(last_line)
        return payload.get("hash")
    except Exception:
        return None


def _hash_payload(prev_hash: str, payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(prev_hash.encode("utf-8") + encoded).hexdigest()


def _sanitize_data(data: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = dict(data)
    if "token" in sanitized:
        token = str(sanitized["token"])
        sanitized["token_hash"] = hashlib.sha256(token.encode("utf-8")).hexdigest()
        sanitized.pop("token", None)
    return sanitized


def log_action(action: str, data: Dict[str, Any]) -> bool:
    if not LOG_ENABLED:
        return False
    global _last_hash
    if _last_hash is None:
        _last_hash = _load_last_hash() or "0" * 64
    payload = {
        "action": action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": _sanitize_data(data),
        "prev_hash": _last_hash,
    }
    payload["hash"] = _hash_payload(_last_hash, payload)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
        _last_hash = payload["hash"]
        return True
    except OSError:
        return False
