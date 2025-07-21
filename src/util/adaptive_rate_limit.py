import statistics
from typing import Iterable


def compute_rate_limit(
    recent_counts: Iterable[int], base_rate: int = 60, multiplier: float = 1.5
) -> int:
    """Compute a new per-minute rate limit based on recent request counts.

    If the average of recent_counts exceeds base_rate * multiplier, the new limit
    is decreased by half. If the average falls below base_rate * 0.5, the limit
    is increased by 50%. Otherwise the base_rate is returned.
    """
    counts = list(recent_counts)
    if not counts:
        return base_rate
    avg = statistics.mean(counts)
    if avg > base_rate * multiplier:
        return int(base_rate * 0.5)
    if avg < base_rate * 0.5:
        return int(base_rate * 1.5)
    return base_rate
