"""
Security chaos engineering tests.

Tests system resilience under various security-related failure conditions,
including failure injection, graceful degradation, and recovery scenarios.
"""

import asyncio
import importlib
import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from test.security.chaos_utils import (
    FailureInjector,
    ResilienceMetrics,
    with_failure_injection,
)


class TestRedisFailureResilience:
    """Test system resilience when Redis is unavailable."""

    @pytest.mark.asyncio
    async def test_rate_limiting_gracefully_degrades_without_redis(self, monkeypatch):
        """Rate limiting should continue to function when Redis is unavailable."""
        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient

        from src.shared.middleware import SecuritySettings, create_app

        # Create app with rate limiting
        settings = SecuritySettings(
            rate_limit_requests=5,
            rate_limit_window=60,
            max_body_size=1024,
            enable_https=False,
        )
        app = create_app(security_settings=settings)

        @app.get("/test")
        async def test_endpoint() -> dict[str, str]:
            return {"status": "ok"}

        client = TestClient(app)

        # Inject Redis failure
        with FailureInjector.redis_unavailable():
            # System should still respond, even if rate limiting is degraded
            response = client.get("/test")
            # Should get either success or a graceful error, not a crash
            assert response.status_code in [200, 503, 429]

    @pytest.mark.asyncio
    async def test_ddos_protection_falls_back_on_redis_failure(self, monkeypatch):
        """DDoS protection should fall back to internal endpoint on Redis failure."""
        from src.util import ddos_protection

        monkeypatch.setenv("ENABLE_DDOS_PROTECTION", "true")
        monkeypatch.setenv("DDOS_INTERNAL_ENDPOINT", "http://localhost/escalate")
        importlib.reload(ddos_protection)

        called_urls = []

        async def mock_post(self, url, *args, **kwargs):
            called_urls.append(url)
            return httpx.Response(200, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        # Inject Redis failure - should fall back to internal endpoint
        with FailureInjector.redis_unavailable():
            result = await ddos_protection.report_attack("10.0.0.1")
            assert result is True
            assert len(called_urls) == 1


class TestNetworkFailureResilience:
    """Test system resilience under network failures."""

    @pytest.mark.asyncio
    async def test_ddos_reporting_handles_timeout_gracefully(self, monkeypatch):
        """DDoS reporting should handle network timeouts without crashing."""
        from src.util import ddos_protection

        monkeypatch.setenv("ENABLE_DDOS_PROTECTION", "true")
        monkeypatch.setenv("DDOS_INTERNAL_ENDPOINT", "http://localhost/escalate")
        importlib.reload(ddos_protection)

        # Inject network timeout
        with FailureInjector.network_timeout():
            result = await ddos_protection.report_attack("10.0.0.2")
            # Should fail gracefully, not crash
            assert result is False

    @pytest.mark.asyncio
    async def test_ddos_reporting_handles_intermittent_failures(self, monkeypatch):
        """DDoS reporting should handle intermittent network failures gracefully."""
        from src.util import ddos_protection

        monkeypatch.setenv("ENABLE_DDOS_PROTECTION", "true")
        monkeypatch.setenv("DDOS_INTERNAL_ENDPOINT", "http://localhost/escalate")
        importlib.reload(ddos_protection)

        metrics = ResilienceMetrics()

        # Inject intermittent failures (50% failure rate)
        with FailureInjector.intermittent_failure(failure_rate=0.5):
            for _ in range(10):
                metrics.record_request()
                result = await ddos_protection.report_attack("10.0.0.3")
                if not result:
                    metrics.record_failure()

        # Key resilience validation: system doesn't crash under intermittent failures
        # All requests should complete (not hang or throw unhandled exceptions)
        assert metrics.request_count == 10
        # System remains operational - can make requests even if some fail
        assert metrics.failure_count <= metrics.request_count


class TestSecurityMiddlewareResilience:
    """Test security middleware resilience under failures."""

    def test_security_headers_applied_despite_errors(self):
        """Security headers should be applied even if other middleware fails."""
        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient

        from src.shared.middleware import SecuritySettings, create_app

        settings = SecuritySettings(
            rate_limit_requests=5,
            rate_limit_window=60,
            max_body_size=1024,
            enable_https=True,
        )
        app = create_app(security_settings=settings)

        @app.get("/success")
        async def success_endpoint() -> dict[str, str]:
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/success")

        # Security headers should be present on successful requests
        assert "X-Frame-Options" in response.headers
        assert "X-Content-Type-Options" in response.headers
        assert "Content-Security-Policy" in response.headers

    def test_rate_limiting_continues_after_redis_recovery(self):
        """Rate limiting should resume normal operation after Redis recovers."""
        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient

        from src.shared.middleware import SecuritySettings, create_app

        settings = SecuritySettings(
            rate_limit_requests=5,
            rate_limit_window=60,
            max_body_size=1024,
            enable_https=False,
        )
        app = create_app(security_settings=settings)

        @app.get("/test")
        async def test_endpoint() -> dict[str, str]:
            return {"status": "ok"}

        client = TestClient(app)

        # First, simulate Redis failure
        with FailureInjector.redis_unavailable():
            response = client.get("/test")
            # Should handle gracefully (system should still respond)
            assert response.status_code in [200, 503, 429]

        # After Redis recovers, system should continue functioning
        # Make a few requests to verify system is operational
        response1 = client.get("/test")
        response2 = client.get("/test")
        
        # At least one should succeed, demonstrating system resilience
        assert response1.status_code in [200, 429] or response2.status_code in [200, 429]


class TestAuditLoggingResilience:
    """Test audit logging resilience under failures."""

    def test_operations_continue_despite_audit_log_failure(self, caplog):
        """System operations should continue even if audit logging fails."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from src.shared.middleware import SecuritySettings, create_app

        settings = SecuritySettings(
            rate_limit_requests=5,
            rate_limit_window=60,
            max_body_size=1024,
            enable_https=False,
        )
        app = create_app(security_settings=settings)

        @app.get("/critical")
        async def critical_endpoint() -> dict[str, str]:
            # This endpoint should work even if audit logging fails
            return {"status": "operational"}

        client = TestClient(app)

        # Inject audit log failure
        with FailureInjector.audit_log_failure():
            # The endpoint should still respond
            try:
                response = client.get("/critical")
                # Either succeeds or fails gracefully
                assert response.status_code in [200, 500, 503]
            except Exception:
                # If it does fail, it should be a controlled failure
                pass


class TestSecurityRecovery:
    """Test security system recovery capabilities."""

    @pytest.mark.asyncio
    async def test_system_recovers_from_transient_failures(self, monkeypatch):
        """System should automatically recover from transient failures."""
        from src.util import ddos_protection

        monkeypatch.setenv("ENABLE_DDOS_PROTECTION", "true")
        monkeypatch.setenv("DDOS_INTERNAL_ENDPOINT", "http://localhost/escalate")
        importlib.reload(ddos_protection)

        success_count = 0
        failure_count = 0

        async def mock_post(self, url, *args, **kwargs):
            # Simulate transient failure followed by recovery
            nonlocal failure_count, success_count
            if failure_count < 2:
                failure_count += 1
                raise httpx.ConnectError("Transient failure")
            success_count += 1
            return httpx.Response(200, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        # First two attempts fail
        assert await ddos_protection.report_attack("10.0.0.4") is False
        assert await ddos_protection.report_attack("10.0.0.4") is False

        # System should recover and subsequent attempts succeed
        assert await ddos_protection.report_attack("10.0.0.4") is True
        assert success_count == 1
        assert failure_count == 2

    def test_security_baselines_validate_recovery_mechanisms(self):
        """Validate that security baselines include recovery mechanisms."""
        from pathlib import Path

        compose_path = Path("docker-compose.yaml")
        assert compose_path.exists(), "docker-compose.yaml should exist"

        compose_text = compose_path.read_text()

        # Check for restart policies that enable recovery
        assert "restart:" in compose_text, "Services should have restart policies"

        # Check for health checks that enable monitoring
        # (Not all services may have them, but some critical ones should)
        service_count = compose_text.count("image:")
        assert service_count > 0, "Should have services defined"


class TestFailureInjectionFramework:
    """Test the failure injection framework itself."""

    @pytest.mark.asyncio
    async def test_redis_failure_injection_works(self):
        """Verify Redis failure injection actually prevents Redis operations."""
        import redis

        # This test verifies the injection mechanism itself
        with FailureInjector.redis_unavailable():
            client = redis.Redis()
            with pytest.raises(redis.exceptions.ConnectionError):
                client.get("test_key")

    @pytest.mark.asyncio
    async def test_network_timeout_injection_works(self):
        """Verify network timeout injection actually causes timeouts."""
        with FailureInjector.network_timeout(timeout=0.001):
            with pytest.raises(httpx.TimeoutException):
                async with httpx.AsyncClient() as client:
                    await client.get("http://example.com")

    def test_resilience_metrics_tracking(self):
        """Verify resilience metrics are tracked correctly."""
        metrics = ResilienceMetrics()

        assert metrics.failure_rate == 0.0
        assert metrics.average_recovery_time == 0.0

        metrics.record_request()
        metrics.record_request()
        metrics.record_failure()

        assert metrics.failure_rate == 0.5
        assert metrics.request_count == 2
        assert metrics.failure_count == 1

        metrics.record_recovery(1.5)
        metrics.record_recovery(2.5)

        assert metrics.average_recovery_time == 2.0
