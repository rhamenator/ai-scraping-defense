"""Simple crawler registry for token-based authentication."""
from __future__ import annotations

from typing import Dict, Optional

_registered: Dict[str, Dict[str, str]] = {}


def register_crawler(name: str, token: str, purpose: str) -> None:
    """Register or update a crawler token."""
    _registered[token] = {"name": name, "purpose": purpose}


def verify_crawler(token: str, purpose: str | None = None) -> bool:
    """Return True if the token exists and (optionally) matches the given purpose."""
    info = _registered.get(token)
    if not info:
        return False
    if purpose and info.get("purpose") != purpose:
        return False
    return True


def get_crawler_info(token: str) -> Optional[Dict[str, str]]:
    """Return crawler info if registered."""
    return _registered.get(token)
