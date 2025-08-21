"""Metrics interface for the AI service."""

from src.shared.metrics import (  # noqa: F401
    COMMUNITY_REPORTS_ATTEMPTED,
    COMMUNITY_REPORTS_ERRORS_REQUEST,
    COMMUNITY_REPORTS_ERRORS_RESPONSE_DECODE,
    COMMUNITY_REPORTS_ERRORS_STATUS,
    COMMUNITY_REPORTS_ERRORS_TIMEOUT,
    COMMUNITY_REPORTS_ERRORS_UNEXPECTED,
    COMMUNITY_REPORTS_SUCCESS,
    increment_counter_metric,
)

__all__ = [name for name in locals() if not name.startswith("_")]
