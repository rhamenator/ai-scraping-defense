"""Metrics interface for the configuration recommender service."""

from src.shared.metrics import get_metrics  # noqa: F401

__all__ = [name for name in locals() if not name.startswith("_")]
