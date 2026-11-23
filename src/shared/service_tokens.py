"""Short-lived per-caller service tokens for internal service-to-service calls.

Replaces sharing one static API key across all internal callers with audience- and
caller-bound HMAC-SHA256 bearer tokens.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def mint_service_token(
    secret: str,
    *,
    caller: str,
    audience: str,
    ttl_seconds: int = 300,
    now: Optional[float] = None,
) -> str:
    """Create a short-lived, caller- and audience-bound token."""
    issued = int(now if now is not None else time.time())
    payload = {
        "sub": caller,
        "aud": audience,
        "iat": issued,
        "exp": issued + max(1, ttl_seconds),
        "jti": secrets.token_hex(8),
    }
    body = _b64u_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def _parse_claims(token: str, secret: str) -> Optional[dict]:
    if not token or "." not in token or not secret:
        return None
    try:
        body, sig = token.rsplit(".", 1)
        expected_sig = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        return json.loads(_b64u_decode(body).decode("utf-8"))
    except Exception:
        return None


def verify_service_token(
    token: str,
    secret: str,
    *,
    expected_audience: str,
    allowed_callers: set[str] | None = None,
    now: Optional[float] = None,
) -> Optional[dict]:
    """Verify signature, expiration, audience, and optional caller allowlist."""
    claims = _parse_claims(token, secret)
    if not claims:
        return None
    current = now if now is not None else time.time()
    if claims.get("aud") != expected_audience or int(claims.get("exp", 0)) < current:
        return None
    if allowed_callers is not None and claims.get("sub") not in allowed_callers:
        return None
    return claims
