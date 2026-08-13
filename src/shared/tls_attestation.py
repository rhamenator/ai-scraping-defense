"""TLS fingerprint attestation shared by edge and scoring services."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from collections.abc import Iterable

ATTESTATION_VERSION = "v1"
DEFAULT_MAX_AGE_SECONDS = 60
_JA3_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_JA4_PATTERN = re.compile(r"^[a-z0-9]{10}_[0-9a-f]{12}_[0-9a-f]{12}$")
_SOURCE_PATTERN = re.compile(r"^[a-z0-9_-]{1,32}$")
_TOKEN_PATTERN = re.compile(r"^v1:([0-9]{1,20}):([0-9a-f]{64})$")


def normalize_ja3(value: str | None) -> str | None:
    candidate = (value or "").strip().lower()
    return candidate if _JA3_PATTERN.fullmatch(candidate) else None


def normalize_ja4(value: str | None) -> str | None:
    candidate = (value or "").strip().lower()
    return candidate if _JA4_PATTERN.fullmatch(candidate) else None


def normalize_source(value: str | None) -> str | None:
    candidate = (value or "").strip().lower()
    return candidate if _SOURCE_PATTERN.fullmatch(candidate) else None


def _key_bytes(
    key: str | bytes | None = None,
    *,
    environment_name: str = "TLS_FINGERPRINT_ATTESTATION_KEY",
) -> bytes | None:
    configured = key if key is not None else os.getenv(environment_name)
    if configured is None:
        return None
    encoded = (
        configured if isinstance(configured, bytes) else configured.encode("utf-8")
    )
    return encoded if len(encoded) >= 32 else None


def _canonical_message(
    issued_at: int,
    client_ip: str,
    method: str,
    path: str,
    ja3: str | None,
    ja4: str | None,
    source: str,
) -> bytes | None:
    fields = (
        ATTESTATION_VERSION,
        str(issued_at),
        client_ip.strip().lower(),
        method.strip().upper(),
        path,
        ja3 or "",
        ja4 or "",
        source,
    )
    if any("\n" in value or "\r" in value or "\x00" in value for value in fields):
        return None
    return "\n".join(fields).encode("utf-8")


def create_tls_fingerprint_attestation(
    *,
    client_ip: str,
    method: str,
    path: str,
    ja3: str | None,
    ja4: str | None,
    source: str | None,
    key: str | bytes | None = None,
    issued_at: int | None = None,
) -> str | None:
    """Create a short-lived binding for a fingerprint observed at a trusted hop."""

    secret = _key_bytes(key)
    normalized_ja3 = normalize_ja3(ja3)
    normalized_ja4 = normalize_ja4(ja4)
    normalized_source = normalize_source(source)
    if (
        secret is None
        or normalized_source is None
        or not (normalized_ja3 or normalized_ja4)
    ):
        return None
    timestamp = int(time.time()) if issued_at is None else int(issued_at)
    canonical = _canonical_message(
        timestamp,
        client_ip,
        method,
        path,
        normalized_ja3,
        normalized_ja4,
        normalized_source,
    )
    if canonical is None:
        return None
    signature = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    return f"{ATTESTATION_VERSION}:{timestamp}:{signature}"


def verify_tls_fingerprint_attestation(
    token: str | None,
    *,
    client_ip: str,
    method: str,
    path: str,
    ja3: str | None,
    ja4: str | None,
    source: str | None,
    key: str | bytes | None = None,
    previous_key: str | bytes | None = None,
    now: int | None = None,
    max_age_seconds: int | None = None,
) -> bool:
    """Verify freshness, request binding, normalization, and HMAC in constant time."""

    current_secret = _key_bytes(key)
    previous_secret = _key_bytes(
        previous_key,
        environment_name="TLS_FINGERPRINT_ATTESTATION_PREVIOUS_KEY",
    )
    match = _TOKEN_PATTERN.fullmatch((token or "").strip().lower())
    normalized_ja3 = normalize_ja3(ja3)
    normalized_ja4 = normalize_ja4(ja4)
    normalized_source = normalize_source(source)
    if (
        (current_secret is None and previous_secret is None)
        or match is None
        or normalized_source is None
        or not (normalized_ja3 or normalized_ja4)
    ):
        return False
    issued_at = int(match.group(1))
    current = int(time.time()) if now is None else int(now)
    if max_age_seconds is None:
        try:
            max_age_seconds = int(
                os.getenv(
                    "TLS_FINGERPRINT_ATTESTATION_MAX_AGE_SECONDS",
                    str(DEFAULT_MAX_AGE_SECONDS),
                )
            )
        except ValueError:
            return False
    if max_age_seconds <= 0 or abs(current - issued_at) > max_age_seconds:
        return False
    canonical = _canonical_message(
        issued_at,
        client_ip,
        method,
        path,
        normalized_ja3,
        normalized_ja4,
        normalized_source,
    )
    if canonical is None:
        return False
    verified = False
    for secret in (current_secret, previous_secret):
        if secret is not None:
            expected = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
            verified |= hmac.compare_digest(expected, match.group(2))
    return verified


def configured_fingerprint_set(name: str) -> set[str]:
    values: Iterable[str] = os.getenv(name, "").split(",")
    normalizer = normalize_ja3 if name.endswith("JA3") else normalize_ja4
    return {normalized for value in values if (normalized := normalizer(value))}


def tls_risk_signals(
    *, ja3: str | None, ja4: str | None, user_agent: str | None, verified: bool
) -> tuple[bool, bool]:
    """Return (known_bad, browser_profile_mismatch) for verified fingerprints."""

    if not verified:
        return False, False
    normalized_ja3 = normalize_ja3(ja3)
    normalized_ja4 = normalize_ja4(ja4)
    known_bad = normalized_ja3 in configured_fingerprint_set(
        "TLS_KNOWN_BAD_JA3"
    ) or normalized_ja4 in configured_fingerprint_set("TLS_KNOWN_BAD_JA4")
    ua = (user_agent or "").lower()
    claims_modern_browser = "mozilla/5.0" in ua and any(
        marker in ua
        for marker in ("chrome/", "crios/", "firefox/", "fxios/", "safari/", "edg/")
    )
    profile = normalized_ja4[:3] if normalized_ja4 else ""
    mismatch = (
        claims_modern_browser
        and bool(normalized_ja4)
        and profile not in {"t12", "t13", "q12", "q13"}
    )
    return known_bad, mismatch
