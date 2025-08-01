from __future__ import annotations

from typing import Dict

import yaml


def load_pricing(path: str) -> Dict[str, float]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {str(k): float(v) for k, v in data.items()}


class PricingEngine:
    def __init__(self, mapping: Dict[str, float], default_price: float = 0.0):
        self.mapping = mapping
        self.default_price = default_price

    def price_for_path(self, path: str) -> float:
        for prefix, price in self.mapping.items():
            if path.startswith(prefix):
                return price
        return self.default_price
