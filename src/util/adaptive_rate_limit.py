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


def compute_mobile_rate_limit(
    recent_counts: Iterable[int],
    base_rate: int = 30,
    multiplier: float = 1.3,
    is_emulator: bool = False,
    is_rooted: bool = False,
) -> int:
    """Compute adaptive rate limit for mobile API endpoints.

    Mobile endpoints typically have lower rate limits than web endpoints
    due to different usage patterns. Emulators and rooted devices get
    even stricter limits.

    Args:
        recent_counts: Recent request counts for this client
        base_rate: Base requests per minute for mobile clients
        multiplier: Threshold multiplier for adaptive adjustment
        is_emulator: True if device is an emulator
        is_rooted: True if device is rooted/jailbroken

    Returns:
        Adjusted rate limit (requests per minute)
    """
    # Apply more aggressive limits for suspicious devices
    if is_emulator:
        base_rate = int(base_rate * 0.5)
    if is_rooted:
        base_rate = int(base_rate * 0.7)

    counts = list(recent_counts)
    if not counts:
        return base_rate

    avg = statistics.mean(counts)

    # More aggressive throttling for mobile to prevent abuse
    if avg > base_rate * multiplier:
        return max(int(base_rate * 0.4), 5)
    if avg < base_rate * 0.5:
        return int(base_rate * 1.3)

    return base_rate
