from typing import Optional
from src.escalation.escalation_engine import RequestMetadata

def check(metadata: RequestMetadata) -> Optional[float]:
    """Example plugin: add to score if user agent contains 'badbot'."""
    ua = (metadata.user_agent or "").lower()
    if 'badbot' in ua:
        return 0.5
    return 0.0

