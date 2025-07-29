"""Simple WAF attack scoring placeholder."""

from __future__ import annotations


def compute_attack_score(payload: str) -> float:
    """Return a probability that a request payload is malicious."""
    score = 0.0
    lowered = payload.lower()

    suspicious_tokens = ["union select", "<script", "../", "wget ", "curl ", "sleep("]
    if any(x in lowered for x in suspicious_tokens):
        score += 0.7

    if "select" in lowered and "from" in lowered:
        score += 0.4
    if any(x in lowered for x in ("--", "/*", ";--", "drop table")):
        score += 0.3

    return min(score, 1.0)
