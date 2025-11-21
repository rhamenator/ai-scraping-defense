"""Metrics interface for the configuration recommender service."""

from src.shared.metrics import (  # noqa: F401
    SECURITY_COMPLIANCE_SCORE,
    SECURITY_DETECTION_COVERAGE,
    SECURITY_POLICY_UPDATES,
    SECURITY_POLICY_VERSION,
    SECURITY_RESPONSE_READINESS,
    get_metrics,
)

__all__ = [name for name in locals() if not name.startswith("_")]
