"""Configurable Zero Trust risk scoring for request and identity signals."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(value, maximum))


@dataclass(frozen=True)
class RiskPolicy:
    """Weights and thresholds for risk scoring."""

    vpn_weight: float = 0.2
    high_frequency_weight: float = 0.15
    empty_user_agent_weight: float = 0.15
    malicious_ip_weight: float = 0.2
    anomaly_weight: float = 0.2
    geo_velocity_weight: float = 0.05
    impossible_travel_weight: float = 0.05
    auth_failure_weight: float = 0.1
    anomaly_threshold: float = 0.7
    auth_failure_threshold: float = 3.0

    @classmethod
    def from_env(cls) -> "RiskPolicy":
        return cls(
            vpn_weight=_env_float("RISK_SCORE_WEIGHT_VPN", cls.vpn_weight),
            high_frequency_weight=_env_float(
                "RISK_SCORE_WEIGHT_HIGH_FREQ", cls.high_frequency_weight
            ),
            empty_user_agent_weight=_env_float(
                "RISK_SCORE_WEIGHT_EMPTY_UA", cls.empty_user_agent_weight
            ),
            malicious_ip_weight=_env_float(
                "RISK_SCORE_WEIGHT_MALICIOUS_IP", cls.malicious_ip_weight
            ),
            anomaly_weight=_env_float(
                "RISK_SCORE_WEIGHT_ANOMALY", cls.anomaly_weight
            ),
            geo_velocity_weight=_env_float(
                "RISK_SCORE_WEIGHT_GEO_VELOCITY", cls.geo_velocity_weight
            ),
            impossible_travel_weight=_env_float(
                "RISK_SCORE_WEIGHT_IMPOSSIBLE_TRAVEL",
                cls.impossible_travel_weight,
            ),
            auth_failure_weight=_env_float(
                "RISK_SCORE_WEIGHT_AUTH_FAILURE", cls.auth_failure_weight
            ),
            anomaly_threshold=_env_float(
                "RISK_SCORE_ANOMALY_THRESHOLD", cls.anomaly_threshold
            ),
            auth_failure_threshold=max(
                _env_float(
                    "RISK_SCORE_AUTH_FAILURE_THRESHOLD", cls.auth_failure_threshold
                ),
                1.0,
            ),
        )

    def total_weight(self) -> float:
        return sum(
            (
                self.vpn_weight,
                self.high_frequency_weight,
                self.empty_user_agent_weight,
                self.malicious_ip_weight,
                self.anomaly_weight,
                self.geo_velocity_weight,
                self.impossible_travel_weight,
                self.auth_failure_weight,
            )
        )


class RiskScorer:
    """Policy-driven risk scoring implementation."""

    def __init__(self, policy: RiskPolicy | None = None):
        self.policy = policy or RiskPolicy.from_env()

    def score_breakdown(self, features: Mapping[str, float]) -> dict[str, float]:
        """Return weighted contributions before normalization."""
        anomaly_score = _clamp(float(features.get("anomaly_score", 0.0) or 0.0))
        auth_failures = max(float(features.get("auth_failures", 0.0) or 0.0), 0.0)
        geo_velocity_risk = _clamp(float(features.get("geo_velocity_risk", 0.0) or 0.0))

        breakdown = {
            "vpn": self.policy.vpn_weight if features.get("is_vpn") else 0.0,
            "high_frequency": (
                self.policy.high_frequency_weight if features.get("high_freq") else 0.0
            ),
            "empty_user_agent": (
                self.policy.empty_user_agent_weight
                if features.get("ua_is_empty")
                else 0.0
            ),
            "malicious_ip": (
                self.policy.malicious_ip_weight
                if features.get("is_malicious_ip")
                else 0.0
            ),
            "anomaly": (
                self.policy.anomaly_weight
                * _clamp(
                    (anomaly_score - self.policy.anomaly_threshold)
                    / max(1.0 - self.policy.anomaly_threshold, 0.01)
                )
                if anomaly_score >= self.policy.anomaly_threshold
                else 0.0
            ),
            "geo_velocity": self.policy.geo_velocity_weight * geo_velocity_risk,
            "impossible_travel": (
                self.policy.impossible_travel_weight
                if features.get("impossible_travel")
                else 0.0
            ),
            "auth_failures": self.policy.auth_failure_weight
            * _clamp(auth_failures / self.policy.auth_failure_threshold),
        }
        return breakdown

    def score(self, features: Mapping[str, float]) -> float:
        """Return a normalized risk score between 0 and 1."""
        total_weight = self.policy.total_weight()
        if total_weight <= 0:
            return 0.0
        total = sum(self.score_breakdown(features).values())
        return _clamp(total / total_weight)
