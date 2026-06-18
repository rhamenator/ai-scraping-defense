"""Configurable attack scoring using weighted payload signatures."""

from __future__ import annotations

import os
import re
from typing import Iterable


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _pattern_score(payload: str, patterns: Iterable[str], weight: float) -> float:
    if not weight:
        return 0.0
    return weight if any(re.search(pattern, payload) for pattern in patterns) else 0.0


_SIGNATURE_CATEGORIES: tuple[tuple[str, float, tuple[str, ...]], ...] = (
    (
        "ATTACK_SCORE_SQL_WEIGHT",
        0.6,
        (
            r"\bunion\s+select\b",
            r"\bselect\b.+\bfrom\b",
            r"\bdrop\s+table\b",
            r"\binsert\s+into\b",
            r"\bor\s+1=1\b",
        ),
    ),
    (
        "ATTACK_SCORE_XSS_WEIGHT",
        0.1,
        (
            r"<script\b",
            r"javascript:",
            r"onerror\s*=",
            r"onload\s*=",
        ),
    ),
    (
        "ATTACK_SCORE_TRAVERSAL_WEIGHT",
        0.075,
        (
            r"\.\./",
            r"\.\.\\",
            r"%2e%2e%2f",
            r"/etc/passwd",
            r"\\windows\\system32",
        ),
    ),
    (
        "ATTACK_SCORE_COMMAND_WEIGHT",
        0.075,
        (
            r"\b(wget|curl|powershell|bash|sh)\b",
            r"`[^`]+`",
            r"\$\(.+\)",
            r"\bsleep\s*\(",
        ),
    ),
    (
        "ATTACK_SCORE_OBFUSCATION_WEIGHT",
        0.15,
        (
            r"/\*",
            r"--",
            r";--",
            r"%3cscript",
            r"base64,",
        ),
    ),
)


def compute_attack_score(payload: str) -> float:
    """Return a normalized probability that a request payload is malicious."""
    lowered = (payload or "").lower()
    if not lowered:
        return 0.0

    weights = [_env_float(name, default) for name, default, _ in _SIGNATURE_CATEGORIES]
    score = sum(
        _pattern_score(lowered, patterns, weight)
        for weight, (_, _, patterns) in zip(weights, _SIGNATURE_CATEGORIES)
    )
    total_weight = max(sum(weights), 0.01)
    return max(0.0, min(score / total_weight, 1.0))
