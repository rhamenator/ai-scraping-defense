"""Timing-safe operations to protect against side-channel attacks.

This module provides utilities to mitigate timing-based side-channel attacks
by ensuring that sensitive operations take constant time regardless of the
input values, and by adding controlled randomization to prevent timing analysis.
"""

import hashlib
import hmac
import secrets
import time
from typing import Any, Optional


def compare_strings_safe(a: str, b: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks.

    Uses secrets.compare_digest which is designed to compare values in
    constant time regardless of the length of common prefix.

    Args:
        a: First string to compare
        b: Second string to compare

    Returns:
        True if strings are equal, False otherwise
    """
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    return secrets.compare_digest(a, b)


def compare_bytes_safe(a: bytes, b: bytes) -> bool:
    """Compare two byte sequences in constant time.

    Args:
        a: First byte sequence
        b: Second byte sequence

    Returns:
        True if byte sequences are equal, False otherwise
    """
    if not isinstance(a, bytes) or not isinstance(b, bytes):
        return False
    return secrets.compare_digest(a, b)


def verify_hmac_safe(
    key: bytes, message: bytes, signature: str, algorithm: str = "sha256"
) -> bool:
    """Verify HMAC signature in constant time.

    Args:
        key: Secret key for HMAC
        message: Message that was signed
        signature: Hex-encoded signature to verify
        algorithm: Hash algorithm to use (default: sha256)

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        expected = hmac.new(key, message, algorithm).hexdigest()
        return secrets.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False


def add_timing_jitter(
    min_delay_ms: float = 10.0, max_delay_ms: float = 50.0
) -> None:
    """Add random timing jitter to prevent timing analysis.

    This function adds a small random delay to sensitive operations to make
    timing-based side-channel attacks more difficult. The delay is
    cryptographically random to prevent prediction.

    Args:
        min_delay_ms: Minimum delay in milliseconds (default: 10ms)
        max_delay_ms: Maximum delay in milliseconds (default: 50ms)
    """
    if min_delay_ms < 0 or max_delay_ms < min_delay_ms:
        raise ValueError("Invalid delay range")

    # Generate cryptographically secure random delay
    delay_ms = min_delay_ms + (
        secrets.randbelow(int((max_delay_ms - min_delay_ms) * 1000)) / 1000.0
    )
    time.sleep(delay_ms / 1000.0)


def constant_time_compare_json(a: Any, b: Any) -> bool:
    """Compare two JSON-serializable objects in constant time.

    This creates a deterministic hash of both objects and compares them
    using constant-time comparison. Note that the serialization itself
    may not be constant-time, but this provides reasonable protection
    for most use cases.

    Args:
        a: First object to compare
        b: Second object to compare

    Returns:
        True if objects serialize to the same value, False otherwise
    """
    try:
        import json

        # Sort keys for deterministic serialization
        a_json = json.dumps(a, sort_keys=True, separators=(",", ":"))
        b_json = json.dumps(b, sort_keys=True, separators=(",", ":"))

        # Hash both JSON strings
        a_hash = hashlib.sha256(a_json.encode()).digest()
        b_hash = hashlib.sha256(b_json.encode()).digest()

        return secrets.compare_digest(a_hash, b_hash)
    except (TypeError, ValueError):
        return False


class TimingSafeValidator:
    """Context manager for timing-safe validation operations.

    This class ensures that validation operations take a consistent amount
    of time regardless of when they fail, making timing attacks harder.
    """

    def __init__(
        self,
        min_duration_ms: float = 100.0,
        add_jitter: bool = True,
        jitter_range_ms: tuple[float, float] = (10.0, 50.0),
    ):
        """Initialize the timing-safe validator.

        Args:
            min_duration_ms: Minimum duration for the validation operation
            add_jitter: Whether to add random jitter on top of min duration
            jitter_range_ms: Range for random jitter in milliseconds
        """
        self.min_duration_ms = min_duration_ms
        self.add_jitter = add_jitter
        self.jitter_range_ms = jitter_range_ms
        self.start_time: Optional[float] = None

    def __enter__(self):
        """Start timing the validation operation."""
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure minimum duration and add jitter if configured."""
        if self.start_time is None:
            return

        elapsed_ms = (time.perf_counter() - self.start_time) * 1000.0

        # Calculate remaining time to meet minimum duration
        remaining_ms = max(0, self.min_duration_ms - elapsed_ms)

        if remaining_ms > 0:
            time.sleep(remaining_ms / 1000.0)

        # Add additional jitter if configured
        if self.add_jitter:
            min_jitter, max_jitter = self.jitter_range_ms
            jitter_ms = min_jitter + (
                secrets.randbelow(int((max_jitter - min_jitter) * 1000)) / 1000.0
            )
            time.sleep(jitter_ms / 1000.0)


def generate_secure_token(nbytes: int = 32) -> str:
    """Generate a cryptographically secure random token.

    Args:
        nbytes: Number of random bytes to generate (default: 32)

    Returns:
        URL-safe base64-encoded token string
    """
    return secrets.token_urlsafe(nbytes)


def generate_secure_hex(nbytes: int = 32) -> str:
    """Generate a cryptographically secure random hex string.

    Args:
        nbytes: Number of random bytes to generate (default: 32)

    Returns:
        Hex-encoded token string
    """
    return secrets.token_hex(nbytes)
