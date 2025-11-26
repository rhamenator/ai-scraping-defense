"""Tests for timing-safe operations module."""

import time
from unittest.mock import patch

import pytest

from src.shared.timing_safe import (
    TimingSafeValidator,
    add_timing_jitter,
    compare_bytes_safe,
    compare_strings_safe,
    constant_time_compare_json,
    generate_secure_hex,
    generate_secure_token,
    verify_hmac_safe,
)


class TestCompareStringsSafe:
    """Tests for compare_strings_safe function."""

    def test_equal_strings(self):
        """Test that equal strings return True."""
        assert compare_strings_safe("hello", "hello") is True
        assert compare_strings_safe("", "") is True
        assert compare_strings_safe("test123", "test123") is True

    def test_different_strings(self):
        """Test that different strings return False."""
        assert compare_strings_safe("hello", "world") is False
        assert compare_strings_safe("test", "Test") is False
        assert compare_strings_safe("abc", "abcd") is False

    def test_invalid_types(self):
        """Test that invalid types return False."""
        assert compare_strings_safe("hello", None) is False
        assert compare_strings_safe(None, "hello") is False
        assert compare_strings_safe(123, "hello") is False
        assert compare_strings_safe("hello", 123) is False


class TestCompareBytesSafe:
    """Tests for compare_bytes_safe function."""

    def test_equal_bytes(self):
        """Test that equal byte sequences return True."""
        assert compare_bytes_safe(b"hello", b"hello") is True
        assert compare_bytes_safe(b"", b"") is True
        assert compare_bytes_safe(b"\x00\x01\x02", b"\x00\x01\x02") is True

    def test_different_bytes(self):
        """Test that different byte sequences return False."""
        assert compare_bytes_safe(b"hello", b"world") is False
        assert compare_bytes_safe(b"\x00", b"\x01") is False
        assert compare_bytes_safe(b"abc", b"abcd") is False

    def test_invalid_types(self):
        """Test that invalid types return False."""
        assert compare_bytes_safe(b"hello", None) is False
        assert compare_bytes_safe(None, b"hello") is False
        assert compare_bytes_safe("hello", b"hello") is False
        assert compare_bytes_safe(b"hello", "hello") is False


class TestVerifyHmacSafe:
    """Tests for verify_hmac_safe function."""

    def test_valid_hmac(self):
        """Test that valid HMAC signatures are accepted."""
        import hmac

        key = b"secret_key"
        message = b"test message"
        signature = hmac.new(key, message, "sha256").hexdigest()

        assert verify_hmac_safe(key, message, signature) is True

    def test_invalid_hmac(self):
        """Test that invalid HMAC signatures are rejected."""
        key = b"secret_key"
        message = b"test message"
        wrong_signature = "0" * 64  # Invalid signature

        assert verify_hmac_safe(key, message, wrong_signature) is False

    def test_wrong_key(self):
        """Test that HMAC with wrong key is rejected."""
        import hmac

        key = b"secret_key"
        wrong_key = b"wrong_key"
        message = b"test message"
        signature = hmac.new(key, message, "sha256").hexdigest()

        assert verify_hmac_safe(wrong_key, message, signature) is False

    def test_different_algorithms(self):
        """Test HMAC verification with different algorithms."""
        import hmac

        key = b"secret_key"
        message = b"test message"

        # Test with sha1
        signature_sha1 = hmac.new(key, message, "sha1").hexdigest()
        assert verify_hmac_safe(key, message, signature_sha1, "sha1") is True

        # Test with sha512
        signature_sha512 = hmac.new(key, message, "sha512").hexdigest()
        assert verify_hmac_safe(key, message, signature_sha512, "sha512") is True

    def test_invalid_inputs(self):
        """Test handling of invalid inputs."""
        assert verify_hmac_safe(b"key", b"message", None) is False
        assert verify_hmac_safe(None, b"message", "sig") is False


class TestAddTimingJitter:
    """Tests for add_timing_jitter function."""

    def test_adds_delay(self):
        """Test that jitter adds actual delay."""
        start = time.perf_counter()
        add_timing_jitter(min_delay_ms=10.0, max_delay_ms=20.0)
        elapsed = (time.perf_counter() - start) * 1000.0

        # Should be at least 10ms
        assert elapsed >= 9.0  # Allow small tolerance
        # Should not exceed 25ms (20ms + tolerance)
        assert elapsed <= 25.0

    def test_default_parameters(self):
        """Test jitter with default parameters."""
        start = time.perf_counter()
        add_timing_jitter()
        elapsed = (time.perf_counter() - start) * 1000.0

        # Should be at least 10ms by default
        assert elapsed >= 9.0
        # Should not exceed 55ms (50ms + tolerance)
        assert elapsed <= 55.0

    def test_invalid_range(self):
        """Test that invalid delay ranges raise ValueError."""
        with pytest.raises(ValueError):
            add_timing_jitter(min_delay_ms=-1.0, max_delay_ms=10.0)

        with pytest.raises(ValueError):
            add_timing_jitter(min_delay_ms=20.0, max_delay_ms=10.0)


class TestConstantTimeCompareJson:
    """Tests for constant_time_compare_json function."""

    def test_equal_dicts(self):
        """Test that equal dictionaries return True."""
        a = {"key": "value", "num": 42}
        b = {"key": "value", "num": 42}
        assert constant_time_compare_json(a, b) is True

    def test_equal_dicts_different_order(self):
        """Test that dictionaries with different key order are equal."""
        a = {"a": 1, "b": 2, "c": 3}
        b = {"c": 3, "b": 2, "a": 1}
        assert constant_time_compare_json(a, b) is True

    def test_different_dicts(self):
        """Test that different dictionaries return False."""
        a = {"key": "value1"}
        b = {"key": "value2"}
        assert constant_time_compare_json(a, b) is False

    def test_different_types(self):
        """Test that different types return False."""
        assert constant_time_compare_json({"key": "value"}, ["key", "value"]) is False

    def test_nested_structures(self):
        """Test comparison of nested structures."""
        a = {"outer": {"inner": [1, 2, 3]}}
        b = {"outer": {"inner": [1, 2, 3]}}
        assert constant_time_compare_json(a, b) is True

        c = {"outer": {"inner": [1, 2, 4]}}
        assert constant_time_compare_json(a, c) is False

    def test_non_serializable(self):
        """Test handling of non-JSON-serializable objects."""
        # Functions are not JSON serializable
        assert constant_time_compare_json(lambda x: x, lambda x: x) is False


class TestTimingSafeValidator:
    """Tests for TimingSafeValidator context manager."""

    def test_enforces_minimum_duration(self):
        """Test that minimum duration is enforced."""
        min_duration = 100.0  # 100ms
        start = time.perf_counter()

        with TimingSafeValidator(
            min_duration_ms=min_duration, add_jitter=False
        ):
            # Fast operation (< 100ms)
            time.sleep(0.01)  # 10ms

        elapsed = (time.perf_counter() - start) * 1000.0

        # Should take at least min_duration
        assert elapsed >= min_duration - 5.0  # Small tolerance

    def test_does_not_extend_long_operations(self):
        """Test that long operations are not extended unnecessarily."""
        min_duration = 50.0  # 50ms
        start = time.perf_counter()

        with TimingSafeValidator(
            min_duration_ms=min_duration, add_jitter=False
        ):
            # Slow operation (> 50ms)
            time.sleep(0.06)  # 60ms

        elapsed = (time.perf_counter() - start) * 1000.0

        # Should be close to actual operation time
        assert 55.0 <= elapsed <= 70.0

    def test_adds_jitter(self):
        """Test that jitter is added when configured."""
        min_duration = 50.0
        jitter_range = (10.0, 20.0)
        start = time.perf_counter()

        with TimingSafeValidator(
            min_duration_ms=min_duration,
            add_jitter=True,
            jitter_range_ms=jitter_range,
        ):
            pass  # Instant operation

        elapsed = (time.perf_counter() - start) * 1000.0

        # Should be min_duration + at least min_jitter
        assert elapsed >= min_duration + jitter_range[0] - 5.0
        # Should not exceed min_duration + max_jitter + tolerance
        assert elapsed <= min_duration + jitter_range[1] + 10.0

    def test_works_with_exceptions(self):
        """Test that timing is enforced even when exceptions occur."""
        min_duration = 100.0
        start = time.perf_counter()

        with pytest.raises(ValueError):
            with TimingSafeValidator(
                min_duration_ms=min_duration, add_jitter=False
            ):
                raise ValueError("Test exception")

        elapsed = (time.perf_counter() - start) * 1000.0

        # Should still enforce minimum duration
        assert elapsed >= min_duration - 5.0


class TestGenerateSecureToken:
    """Tests for generate_secure_token function."""

    def test_generates_token(self):
        """Test that token is generated."""
        token = generate_secure_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_tokens_are_unique(self):
        """Test that generated tokens are unique."""
        tokens = [generate_secure_token() for _ in range(100)]
        assert len(set(tokens)) == 100  # All unique

    def test_custom_length(self):
        """Test token generation with custom length."""
        token = generate_secure_token(nbytes=16)
        assert isinstance(token, str)
        # URL-safe base64 encoding expands the length
        assert len(token) >= 16


class TestGenerateSecureHex:
    """Tests for generate_secure_hex function."""

    def test_generates_hex(self):
        """Test that hex string is generated."""
        hex_str = generate_secure_hex()
        assert isinstance(hex_str, str)
        assert len(hex_str) == 64  # 32 bytes = 64 hex chars

    def test_hex_format(self):
        """Test that output is valid hex."""
        hex_str = generate_secure_hex()
        # Should not raise
        int(hex_str, 16)

    def test_hex_unique(self):
        """Test that generated hex strings are unique."""
        hex_strs = [generate_secure_hex() for _ in range(100)]
        assert len(set(hex_strs)) == 100  # All unique

    def test_custom_length(self):
        """Test hex generation with custom length."""
        hex_str = generate_secure_hex(nbytes=16)
        assert len(hex_str) == 32  # 16 bytes = 32 hex chars
