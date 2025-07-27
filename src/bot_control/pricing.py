"""Minimal pay-per-crawl accounting."""
from __future__ import annotations

from typing import Dict

_default_price = 0.001
_prices: Dict[str, float] = {}
_usage: Dict[str, float] = {}


def set_price(purpose: str, price: float) -> None:
    """Set the crawl price for a specific purpose."""
    _prices[purpose] = max(0.0, price)


def record_crawl(token: str, purpose: str) -> float:
    """Record a crawl and return the charge for this request."""
    price = _prices.get(purpose, _default_price)
    _usage[token] = _usage.get(token, 0.0) + price
    return price


def get_usage(token: str) -> float:
    """Return the current owed balance for a token."""
    return _usage.get(token, 0.0)
