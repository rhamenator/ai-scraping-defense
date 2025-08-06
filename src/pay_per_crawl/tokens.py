"""Tokenization helpers for payment data."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from typing import Optional

_DIGIT_RE = re.compile(r"\D")


def _sanitize_card(number: str) -> str:
    """Return the digits from ``number`` with all other chars removed."""
    return _DIGIT_RE.sub("", number)


def _luhn_valid(number: str) -> bool:
    """Return ``True`` if ``number`` passes the Luhn checksum."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 12 or len(digits) > 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def secure_hash(
    value: str, *, secret: Optional[str] = None, salt: Optional[str] = None
) -> str:
    """Return an HMAC-SHA3-512 digest for ``value``.

    ``secret`` defaults to the ``PAYMENT_TOKEN_SECRET`` environment variable.
    ``salt`` may be supplied to produce distinct digests for the same value.
    """
    secret_key = secret or os.getenv("PAYMENT_TOKEN_SECRET")
    if not secret_key:
        raise ValueError("token secret required")
    payload = value.encode("utf-8")
    if salt:
        payload += salt.encode("utf-8")
    return hmac.new(secret_key.encode("utf-8"), payload, hashlib.sha3_512).hexdigest()


def tokenize_card(
    card_number: str, *, secret: Optional[str] = None, salt: Optional[str] = None
) -> str:
    """Return a secure token for ``card_number`` after validation.

    The number is sanitized, validated with the Luhn algorithm, then hashed
    using :func:`secure_hash` so the raw value is never persisted.
    """
    cleaned = _sanitize_card(card_number)
    if not _luhn_valid(cleaned):
        raise ValueError("invalid card number")
    token = secure_hash(cleaned, secret=secret, salt=salt)
    # best effort to clear sensitive data
    del cleaned  # pragma: no cover - can't reliably ensure in CPython
    return token

