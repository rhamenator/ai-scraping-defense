from __future__ import annotations

import logging
from typing import Dict

from src.util.secure_xml_parser import safe_yaml_load_file


def load_pricing(path: str) -> Dict[str, float]:
    """Load pricing configuration from a YAML file using secure parsing.

    Args:
        path: Path to the YAML pricing configuration file

    Returns:
        Dictionary mapping path prefixes to pricing values
    """
    try:
        data = safe_yaml_load_file(path) or {}
        return {str(k): float(v) for k, v in data.items()}
    except (OSError, Exception) as exc:
        logging.warning("Failed to load pricing from %s: %s", path, exc)
        return {}


class PricingEngine:
    def __init__(self, mapping: Dict[str, float], default_price: float = 0.0):
        self.mapping = mapping
        self.default_price = default_price

    def price_for_path(self, path: str) -> float:
        for prefix, price in self.mapping.items():
            if path.startswith(prefix):
                return price
        return self.default_price
