"""Placeholder Zero Trust risk scoring."""
from __future__ import annotations

from typing import Dict


class RiskScorer:
    """Very naive risk scoring implementation."""

    def score(self, features: Dict[str, float]) -> float:
        score = 0.0
        score += 0.5 if features.get("is_vpn") else 0.0
        score += 0.3 if features.get("high_freq") else 0.0
        score += 0.2 if features.get("anomaly_score", 0) > 0.7 else 0.0
        return min(score, 1.0)
