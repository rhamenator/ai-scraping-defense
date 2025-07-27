"""Simple WAF attack scoring placeholder."""
from __future__ import annotations


def compute_attack_score(payload: str) -> float:
    """Return a probability that a request payload is malicious."""
    score = 0.0
    lowered = payload.lower()
    if any(x in lowered for x in ("union select", "<script", "../")):
        score += 0.7
    if "select" in lowered and "from" in lowered:
        score += 0.5
    if "--" in lowered or "/*" in lowered:
        score += 0.2
    return min(score, 1.0)
