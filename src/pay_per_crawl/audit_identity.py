"""Pseudonymous identifiers for sensitive pay-per-crawl audit fields."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

_EPHEMERAL_AUDIT_KEY = secrets.token_bytes(32)


def audit_token(token: str) -> str:
    """Return a keyed, non-reversible identifier suitable for audit correlation.

    Configure ``CRAWLER_AUDIT_HMAC_KEY`` to keep identifiers stable across
    restarts. Without it, the process-local random key deliberately prevents an
    offline dictionary attack against low-entropy crawler tokens in old logs.
    """

    configured_key = os.getenv("CRAWLER_AUDIT_HMAC_KEY", "").encode("utf-8")
    if configured_key and len(configured_key) < 32:
        raise ValueError("CRAWLER_AUDIT_HMAC_KEY must contain at least 32 bytes")
    key = configured_key or _EPHEMERAL_AUDIT_KEY
    return hmac.new(key, token.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
