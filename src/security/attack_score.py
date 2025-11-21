"""Simple WAF attack scoring placeholder."""

from __future__ import annotations


def compute_attack_score(payload: str, user_agent: str = "") -> float:
    """Return a probability that a request payload is malicious.

    Args:
        payload: Request payload to analyze
        user_agent: User-Agent header (optional, for mobile bot detection)

    Returns:
        Attack score between 0.0 and 1.0
    """
    score = 0.0
    lowered = payload.lower()

    suspicious_tokens = ["union select", "<script", "../", "wget ", "curl ", "sleep("]
    if any(x in lowered for x in suspicious_tokens):
        score += 0.7

    if "select" in lowered and "from" in lowered:
        score += 0.4
    if any(x in lowered for x in ("--", "/*", ";--", "drop table")):
        score += 0.3

    # Mobile-specific attack patterns
    if user_agent:
        ua_lower = user_agent.lower()
        # Detect mobile user agents with suspicious automation patterns
        mobile_bot_indicators = [
            "bot",
            "crawler",
            "spider",
            "scraper",
            "headless",
            "phantom",
            "selenium",
        ]
        # Check if claims to be mobile but has automation indicators
        is_mobile_claim = any(
            x in ua_lower for x in ["iphone", "ipad", "android", "mobile"]
        )
        has_bot_indicators = any(x in ua_lower for x in mobile_bot_indicators)

        if is_mobile_claim and has_bot_indicators:
            score += 0.5

        # Detect spoofed mobile user agents (incomplete or malformed)
        if is_mobile_claim:
            # Real mobile UAs typically have version numbers
            import re

            if not re.search(r"\d+\.\d+", ua_lower):
                score += 0.3

    return min(score, 1.0)
