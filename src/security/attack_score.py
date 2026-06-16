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
    lowered = payload.lower()
    return weight if any(re.search(pattern, lowered) for pattern in patterns) else 0.0


def compute_attack_score(payload: str) -> float:
    """Return a normalized probability that a request payload is malicious."""
    lowered = (payload or "").lower()
    if not lowered:
        return 0.0

    sql_weight = _env_float("ATTACK_SCORE_SQL_WEIGHT", 0.6)
    xss_weight = _env_float("ATTACK_SCORE_XSS_WEIGHT", 0.1)
    traversal_weight = _env_float("ATTACK_SCORE_TRAVERSAL_WEIGHT", 0.075)
    command_weight = _env_float("ATTACK_SCORE_COMMAND_WEIGHT", 0.075)
    obfuscation_weight = _env_float("ATTACK_SCORE_OBFUSCATION_WEIGHT", 0.15)

    score = 0.0
    score += _pattern_score(
        lowered,
        (
            r"\bunion\s+select\b",
            r"\bselect\b.+\bfrom\b",
            r"\bdrop\s+table\b",
            r"\binsert\s+into\b",
            r"\bor\s+1=1\b",
        ),
        sql_weight,
    )
    score += _pattern_score(
        lowered,
        (
            r"<script\b",
            r"javascript:",
            r"onerror\s*=",
            r"onload\s*=",
        ),
        xss_weight,
    )
    score += _pattern_score(
        lowered,
        (
            r"\.\./",
            r"\.\.\\",
            r"%2e%2e%2f",
            r"/etc/passwd",
            r"\\windows\\system32",
        ),
        traversal_weight,
    )
    score += _pattern_score(
        lowered,
        (
            r"\b(wget|curl|powershell|bash|sh)\b",
            r"`[^`]+`",
            r"\$\(.+\)",
            r"\bsleep\s*\(",
        ),
        command_weight,
    )
    score += _pattern_score(
        lowered,
        (
            r"/\*",
            r"--",
            r";--",
            r"%3cscript",
            r"base64,",
        ),
        obfuscation_weight,
    )

    total_weight = max(
        sql_weight
        + xss_weight
        + traversal_weight
        + command_weight
        + obfuscation_weight,
        0.01,
    )
    return max(0.0, min(score / total_weight, 1.0))
