"""Tokenization helpers for payment data."""

from __future__ import annotations

import hashlib
from typing import Optional


def tokenize_card(card_number: str, *, salt: Optional[str] = None) -> str:
    """Return a SHA-256 token for ``card_number``.

    Raw card numbers should never be stored. This helper hashes the
    provided number with an optional ``salt`` to produce a consistent
    token that can safely be stored or logged.
    """
    digest = hashlib.sha256()
    if salt:
        digest.update(salt.encode("utf-8"))
    digest.update(card_number.encode("utf-8"))
    return digest.hexdigest()
