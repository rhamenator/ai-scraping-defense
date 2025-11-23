"""Placeholder Zero Trust risk scoring."""

from __future__ import annotations

from typing import Dict


class RiskScorer:
    """Basic risk scoring implementation."""

    def score(self, features: Dict[str, float]) -> float:
        """Return a risk score between 0 and 1."""
        score = 0.0

        if features.get("is_vpn"):
            score += 0.3
        if features.get("high_freq"):
            score += 0.2
        if features.get("ua_is_empty"):
            score += 0.2
        if features.get("is_malicious_ip"):
            score += 0.3
        if features.get("anomaly_score", 0) > 0.7:
            score += 0.2

        return min(score, 1.0)