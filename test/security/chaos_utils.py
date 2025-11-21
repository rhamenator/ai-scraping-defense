"""
Chaos engineering utilities for security testing.

This module provides failure injection utilities and helpers for testing
system resilience under various security-related failure scenarios.
"""

import asyncio
import contextlib
import functools
import random
from typing import Any, Callable, Optional
from unittest.mock import patch


class FailureInjector:
    """Inject failures into system components for chaos testing."""

    @staticmethod
    @contextlib.contextmanager
    def redis_unavailable():
        """Simulate Redis connection failure."""
        from redis.exceptions import ConnectionError as RedisConnectionError

        def mock_redis_method(*args, **kwargs):
            raise RedisConnectionError("Redis connection failed (chaos injection)")

        with patch("redis.Redis.get", side_effect=mock_redis_method), patch(
            "redis.Redis.set", side_effect=mock_redis_method
        ), patch("redis.Redis.incr", side_effect=mock_redis_method), patch(
            "redis.Redis.expire", side_effect=mock_redis_method
        ), patch("redis.Redis.sadd", side_effect=mock_redis_method), patch(
            "redis.Redis.sismember", side_effect=mock_redis_method
        ):
            yield

    @staticmethod
    @contextlib.contextmanager
    def network_timeout(timeout: float = 0.001):
        """Simulate network timeout for external calls."""
        import httpx

        async def mock_request(*args, **kwargs):
            await asyncio.sleep(timeout)
            raise httpx.TimeoutException("Network timeout (chaos injection)")

        with patch("httpx.AsyncClient.post", side_effect=mock_request), patch(
            "httpx.AsyncClient.get", side_effect=mock_request
        ):
            yield

    @staticmethod
    @contextlib.contextmanager
    def intermittent_failure(failure_rate: float = 0.5):
        """Inject intermittent failures with specified probability.

        Args:
            failure_rate: Probability of failure (0.0-1.0)
        """

        def should_fail():
            return random.random() < failure_rate

        original_post = None
        original_get = None

        async def intermittent_post(self, *args, **kwargs):
            if should_fail():
                import httpx

                raise httpx.ConnectError("Intermittent failure (chaos injection)")
            return await original_post(self, *args, **kwargs)

        async def intermittent_get(self, *args, **kwargs):
            if should_fail():
                import httpx

                raise httpx.ConnectError("Intermittent failure (chaos injection)")
            return await original_get(self, *args, **kwargs)

        import httpx

        original_post = httpx.AsyncClient.post
        original_get = httpx.AsyncClient.get

        with patch("httpx.AsyncClient.post", intermittent_post), patch(
            "httpx.AsyncClient.get", intermittent_get
        ):
            yield

    @staticmethod
    @contextlib.contextmanager
    def slow_response(delay: float = 2.0):
        """Inject artificial latency into responses.

        Args:
            delay: Seconds to delay before responding
        """
        import httpx

        original_post = httpx.AsyncClient.post
        original_get = httpx.AsyncClient.get

        async def delayed_post(self, *args, **kwargs):
            await asyncio.sleep(delay)
            return await original_post(self, *args, **kwargs)

        async def delayed_get(self, *args, **kwargs):
            await asyncio.sleep(delay)
            return await original_get(self, *args, **kwargs)

        with patch("httpx.AsyncClient.post", delayed_post), patch(
            "httpx.AsyncClient.get", delayed_get
        ):
            yield

    @staticmethod
    @contextlib.contextmanager
    def audit_log_failure():
        """Simulate audit logging failure."""
        import logging

        def failing_logger(*args, **kwargs):
            raise IOError("Audit log write failed (chaos injection)")

        # Mock the audit logger's handlers
        with patch.object(logging.Logger, "info", side_effect=failing_logger), patch.object(
            logging.Logger, "warning", side_effect=failing_logger
        ), patch.object(logging.Logger, "error", side_effect=failing_logger):
            yield


class ResilienceMetrics:
    """Track metrics for resilience testing."""

    def __init__(self):
        self.request_count = 0
        self.failure_count = 0
        self.fallback_count = 0
        self.recovery_time = []

    def record_request(self):
        """Record a request attempt."""
        self.request_count += 1

    def record_failure(self):
        """Record a failure."""
        self.failure_count += 1

    def record_fallback(self):
        """Record a fallback activation."""
        self.fallback_count += 1

    def record_recovery(self, time_seconds: float):
        """Record recovery time."""
        self.recovery_time.append(time_seconds)

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate."""
        if self.request_count == 0:
            return 0.0
        return self.failure_count / self.request_count

    @property
    def average_recovery_time(self) -> float:
        """Calculate average recovery time."""
        if not self.recovery_time:
            return 0.0
        return sum(self.recovery_time) / len(self.recovery_time)

    def reset(self):
        """Reset all metrics."""
        self.request_count = 0
        self.failure_count = 0
        self.fallback_count = 0
        self.recovery_time = []


def with_failure_injection(failure_type: str, **kwargs):
    """Decorator for tests that inject failures.

    Args:
        failure_type: Type of failure to inject (redis, network, intermittent, etc.)
        **kwargs: Additional parameters for the failure injector
    """

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **test_kwargs):
            injector = FailureInjector()
            if failure_type == "redis":
                with injector.redis_unavailable():
                    return await func(*args, **test_kwargs)
            elif failure_type == "network":
                with injector.network_timeout(**kwargs):
                    return await func(*args, **test_kwargs)
            elif failure_type == "intermittent":
                with injector.intermittent_failure(**kwargs):
                    return await func(*args, **test_kwargs)
            elif failure_type == "slow":
                with injector.slow_response(**kwargs):
                    return await func(*args, **test_kwargs)
            elif failure_type == "audit":
                with injector.audit_log_failure():
                    return await func(*args, **test_kwargs)
            else:
                raise ValueError(f"Unknown failure type: {failure_type}")

        @functools.wraps(func)
        def sync_wrapper(*args, **test_kwargs):
            injector = FailureInjector()
            if failure_type == "redis":
                with injector.redis_unavailable():
                    return func(*args, **test_kwargs)
            elif failure_type == "audit":
                with injector.audit_log_failure():
                    return func(*args, **test_kwargs)
            else:
                raise ValueError(f"Sync wrapper doesn't support: {failure_type}")

        # Return appropriate wrapper based on whether func is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
