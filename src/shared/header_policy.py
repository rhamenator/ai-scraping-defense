"""Which request headers may travel where (#1904).

Request headers can carry credentials and identity: API keys, session and CSRF tokens, CAPTCHA responses, proxy
credentials, signatures and custom secret headers. Two allowlists keep them from spreading:

* ``internal_headers`` is what the escalation engine itself reads (browser-fingerprint inputs, the original method, and
  the CAPTCHA response it verifies). Everything else is dropped when the tarpit forwards a request to the engine, and
  again when the engine accepts one.
* ``external_headers`` is what may leave the engine for a classifier, a language model, the blocklist record or a
  webhook: ordinary browser-identification headers only. Anything that looks like a credential is refused even if an
  operator adds it to the list, and the CAPTCHA response never leaves the engine.
"""

import os
import re
from typing import Dict, Iterable, Mapping, Optional

# Read by the escalation engine: fingerprinting, the original method, and the CAPTCHA response it verifies.
INTERNAL_HEADER_ALLOWLIST = frozenset(
    {
        "accept",
        "accept-encoding",
        "accept-language",
        "sec-ch-ua",
        "sec-ch-ua-mobile",
        "sec-ch-ua-platform",
        "sec-fetch-dest",
        "sec-fetch-mode",
        "sec-fetch-site",
        "dnt",
        "upgrade-insecure-requests",
        "x-original-method",
        "method",
        "x-captcha-token",
    }
)

# Documented telemetry that may leave the engine. No identity, credential, signature, CSRF or CAPTCHA fields.
EXTERNAL_HEADER_ALLOWLIST = frozenset(
    {
        "accept",
        "accept-encoding",
        "accept-language",
        "sec-ch-ua",
        "sec-ch-ua-mobile",
        "sec-ch-ua-platform",
        "sec-fetch-dest",
        "sec-fetch-mode",
        "sec-fetch-site",
        "dnt",
        "upgrade-insecure-requests",
    }
)

_SENSITIVE_NAME = re.compile(
    r"(auth|cookie|token|secret|passw|key|session|csrf|xsrf|captcha|signature|credential|bearer|jwt|sid\b|proxy-)",
    re.IGNORECASE,
)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_MAX_VALUE = 512
_MAX_TOKEN = 8192
_OPAQUE_TOKEN_HEADERS = frozenset({"x-captcha-token"})


def is_sensitive_header(name: str) -> bool:
    """True for header names that look like credentials, identity or signatures."""
    return bool(_SENSITIVE_NAME.search(name or ""))


def _configured_external_allowlist() -> frozenset:
    """``EXTERNAL_API_HEADER_ALLOWLIST`` (comma-separated) replaces the default list; credential-like names are still refused."""
    raw = os.getenv("EXTERNAL_API_HEADER_ALLOWLIST")
    if raw is None:
        return EXTERNAL_HEADER_ALLOWLIST
    return frozenset(n.strip().lower() for n in raw.split(",") if n.strip())


def _filter(headers: Optional[Mapping[str, object]], allowed: Iterable[str]) -> Dict[str, str]:
    allowed = set(allowed)
    result: Dict[str, str] = {}
    for name, value in (headers or {}).items():
        key = str(name).strip().lower()
        if key not in allowed:
            continue
        cleaned = _CONTROL.sub("", str(value))
        if key in _OPAQUE_TOKEN_HEADERS:
            # An opaque response that the engine submits for verification: truncating it would make a valid response
            # fail, so an oversized one is dropped (and the challenge simply goes unanswered) instead.
            if len(cleaned) <= _MAX_TOKEN:
                result[key] = cleaned
            continue
        result[key] = cleaned[:_MAX_VALUE]
    return result


def _permitted_external() -> set:
    return {n for n in _configured_external_allowlist() if not is_sensitive_header(n)}


def internal_headers(headers: Optional[Mapping[str, object]]) -> Dict[str, str]:
    """Headers the escalation engine may receive and keep in memory.

    Includes any non-credential header an operator listed in ``EXTERNAL_API_HEADER_ALLOWLIST``: it has to survive the
    way in before it can be sent out.
    """
    return _filter(headers, INTERNAL_HEADER_ALLOWLIST | _permitted_external())


def external_headers(headers: Optional[Mapping[str, object]]) -> Dict[str, str]:
    """Headers that may be sent outside the engine (classifiers, models, blocklist records, webhooks)."""
    return _filter(headers, _permitted_external())
