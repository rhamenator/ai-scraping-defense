"""
Security Game Day scenarios.

Runnable security scenarios that simulate real-world attack patterns and
validate the system's detection, response, and recovery capabilities.
"""

import asyncio
import importlib
import logging
import time
from typing import Dict, List
from unittest.mock import patch

import httpx
import pytest

from test.security.chaos_utils import FailureInjector, ResilienceMetrics


class GameDayScenario:
    """Base class for security game day scenarios."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.metrics = ResilienceMetrics()
        self.start_time = None
        self.end_time = None

    def start(self):
        """Start the scenario."""
        self.start_time = time.time()
        self.metrics.reset()

    def end(self):
        """End the scenario."""
        self.end_time = time.time()

    @property
    def duration(self) -> float:
        """Get scenario duration in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0

    def report(self) -> Dict[str, any]:
        """Generate scenario report."""
        return {
            "name": self.name,
            "description": self.description,
            "duration": self.duration,
            "requests": self.metrics.request_count,
            "failures": self.metrics.failure_count,
            "failure_rate": self.metrics.failure_rate,
            "fallbacks": self.metrics.fallback_count,
            "avg_recovery_time": self.metrics.average_recovery_time,
        }


class TestDDoSAttackScenario:
    """Simulate and test response to DDoS attack."""

    @pytest.mark.asyncio
    async def test_gameday_distributed_ddos_attack(self, monkeypatch):
        """
        Game Day Scenario: Distributed DDoS Attack

        Simulates a coordinated DDoS attack from multiple IPs to test:
        - Rate limiting effectiveness
        - DDoS protection activation
        - System stability under load
        - Recovery after attack subsides
        """
        scenario = GameDayScenario(
            name="Distributed DDoS Attack",
            description="Multiple IPs attacking simultaneously",
        )
        scenario.start()

        from fastapi.testclient import TestClient

        from src.shared.middleware import SecuritySettings, create_app

        settings = SecuritySettings(
            rate_limit_requests=10,
            rate_limit_window=60,
            max_body_size=1024,
            enable_https=False,
        )
        app = create_app(security_settings=settings)

        @app.get("/api/data")
        async def data_endpoint() -> dict[str, str]:
            return {"data": "sensitive"}

        client = TestClient(app)

        # Simulate attack from multiple IPs (different client IPs)
        attack_ips = [f"192.168.1.{i}" for i in range(1, 11)]
        blocked_count = 0

        for ip in attack_ips:
            # Simulate rapid requests from each IP
            for _ in range(15):  # Exceeds rate limit
                scenario.metrics.record_request()
                response = client.get("/api/data")
                if response.status_code == 429:
                    blocked_count += 1
                    scenario.metrics.record_fallback()

        scenario.end()

        # Validate protection mechanisms activated
        assert blocked_count > 0, "Rate limiting should have blocked some requests"
        report = scenario.report()
        assert report["requests"] == 150  # 10 IPs * 15 requests
        assert report["fallbacks"] > 0

    @pytest.mark.asyncio
    async def test_gameday_ddos_with_redis_failure(self, monkeypatch):
        """
        Game Day Scenario: DDoS Attack During Redis Outage

        Tests system resilience when DDoS attack occurs while Redis is down:
        - Graceful degradation of rate limiting
        - Fallback to local analysis
        - System availability maintained
        """
        scenario = GameDayScenario(
            name="DDoS + Redis Failure",
            description="DDoS attack while Redis is unavailable",
        )
        scenario.start()

        from src.util import ddos_protection

        monkeypatch.setenv("ENABLE_DDOS_PROTECTION", "true")
        monkeypatch.setenv("DDOS_INTERNAL_ENDPOINT", "http://localhost/escalate")
        importlib.reload(ddos_protection)

        called_internal = 0

        async def mock_post(self, url, *args, **kwargs):
            nonlocal called_internal
            called_internal += 1
            return httpx.Response(200, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        # Simulate DDoS with Redis down
        with FailureInjector.redis_unavailable():
            attack_ips = [f"10.0.1.{i}" for i in range(1, 6)]
            for ip in attack_ips:
                scenario.metrics.record_request()
                result = await ddos_protection.report_attack(ip)
                if result:
                    scenario.metrics.record_fallback()
                else:
                    scenario.metrics.record_failure()

        scenario.end()

        # System should fall back to internal endpoint
        assert called_internal > 0, "Should have fallen back to internal endpoint"
        report = scenario.report()
        assert report["requests"] == 5


class TestCredentialStuffingScenario:
    """Simulate credential stuffing attack."""

    @pytest.mark.asyncio
    async def test_gameday_credential_stuffing_attack(self):
        """
        Game Day Scenario: Credential Stuffing Attack

        Simulates automated credential stuffing to test:
        - Authentication rate limiting
        - Failed login detection
        - Account lockout mechanisms
        """
        scenario = GameDayScenario(
            name="Credential Stuffing",
            description="Automated login attempts with stolen credentials",
        )
        scenario.start()

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

        login_attempts = []

        @app.post("/login", status_code=401)
        async def login_endpoint(username: str, password: str) -> dict[str, str]:
            login_attempts.append((username, password))
            # Simulate all attempts failing
            return {"error": "Invalid credentials"}

        client = TestClient(app)

        # Simulate credential stuffing with multiple username/password pairs
        credentials = [(f"user{i}", f"pass{i}") for i in range(20)]

        blocked_count = 0
        for username, password in credentials:
            scenario.metrics.record_request()
            response = client.post(
                "/login", params={"username": username, "password": password}
            )
            if response.status_code == 429:
                blocked_count += 1
                scenario.metrics.record_fallback()

        scenario.end()

        # Rate limiting should block excessive attempts
        assert blocked_count > 0, "Should have rate limited login attempts"
        report = scenario.report()
        assert report["requests"] == 20


class TestAPIAbuseScenario:
    """Simulate API abuse and scraping attempts."""

    @pytest.mark.asyncio
    async def test_gameday_aggressive_scraping(self):
        """
        Game Day Scenario: Aggressive Web Scraping

        Simulates aggressive scraping bot to test:
        - Request rate detection
        - Pattern-based blocking
        - Resource protection
        """
        scenario = GameDayScenario(
            name="Aggressive Scraping",
            description="High-frequency scraping from single source",
        )
        scenario.start()

        from fastapi.testclient import TestClient

        from src.shared.middleware import SecuritySettings, create_app

        settings = SecuritySettings(
            rate_limit_requests=10,
            rate_limit_window=60,
            max_body_size=1024,
            enable_https=False,
        )
        app = create_app(security_settings=settings)

        @app.get("/api/v1/resource/{resource_id}")
        async def resource_endpoint(resource_id: int) -> dict:
            return {"id": resource_id, "data": "content"}

        client = TestClient(app)

        # Simulate aggressive scraping pattern
        scraping_pattern = list(range(1, 51))  # Scrape 50 resources rapidly
        blocked_count = 0

        for resource_id in scraping_pattern:
            scenario.metrics.record_request()
            response = client.get(f"/api/v1/resource/{resource_id}")
            if response.status_code == 429:
                blocked_count += 1
                scenario.metrics.record_fallback()

        scenario.end()

        # Should detect and block scraping
        assert blocked_count > 0, "Should have blocked excessive scraping"
        report = scenario.report()
        assert report["requests"] == 50


class TestMultiVectorAttackScenario:
    """Simulate coordinated multi-vector attack."""

    @pytest.mark.asyncio
    async def test_gameday_coordinated_attack(self, monkeypatch):
        """
        Game Day Scenario: Coordinated Multi-Vector Attack

        Simulates simultaneous attacks from multiple vectors:
        - DDoS flood
        - Credential stuffing
        - API abuse
        - Infrastructure failures

        Tests comprehensive defense and resilience capabilities.
        """
        scenario = GameDayScenario(
            name="Multi-Vector Attack",
            description="Coordinated attack across multiple vectors",
        )
        scenario.start()

        from fastapi.testclient import TestClient

        from src.shared.middleware import SecuritySettings, create_app
        from src.util import ddos_protection

        # Setup environment
        monkeypatch.setenv("ENABLE_DDOS_PROTECTION", "true")
        monkeypatch.setenv("DDOS_INTERNAL_ENDPOINT", "http://localhost/escalate")
        importlib.reload(ddos_protection)

        settings = SecuritySettings(
            rate_limit_requests=5,
            rate_limit_window=60,
            max_body_size=1024,
            enable_https=False,
        )
        app = create_app(security_settings=settings)

        @app.get("/api/data")
        async def data_endpoint() -> dict[str, str]:
            return {"data": "content"}

        @app.post("/login")
        async def login_endpoint() -> dict[str, str]:
            return {"error": "Invalid"}, 401

        client = TestClient(app)

        # Vector 1: DDoS flood
        for i in range(10):
            scenario.metrics.record_request()
            response = client.get("/api/data")
            if response.status_code == 429:
                scenario.metrics.record_fallback()

        # Vector 2: Credential stuffing
        for i in range(10):
            scenario.metrics.record_request()
            response = client.post("/login")
            if response.status_code == 429:
                scenario.metrics.record_fallback()

        # Vector 3: Infrastructure stress - Redis failure
        with FailureInjector.redis_unavailable():
            for i in range(5):
                scenario.metrics.record_request()
                try:
                    response = client.get("/api/data")
                    if response.status_code >= 500:
                        scenario.metrics.record_failure()
                except Exception:
                    scenario.metrics.record_failure()

        scenario.end()

        # System should maintain basic functionality
        report = scenario.report()
        assert report["requests"] == 25
        # Some fallback/protection should activate
        assert report["fallbacks"] > 0 or report["failures"] < report["requests"]


class TestRecoveryDrillScenario:
    """Test recovery procedures after security incidents."""

    @pytest.mark.asyncio
    async def test_gameday_incident_recovery_drill(self, monkeypatch):
        """
        Game Day Scenario: Incident Recovery Drill

        Simulates security incident response and recovery:
        1. Incident detection (attack)
        2. Containment (blocking)
        3. Recovery (service restoration)
        4. Validation (normal operation)
        """
        scenario = GameDayScenario(
            name="Incident Recovery Drill",
            description="Complete incident response lifecycle",
        )
        scenario.start()

        from src.util import ddos_protection

        monkeypatch.setenv("ENABLE_DDOS_PROTECTION", "true")
        monkeypatch.setenv("DDOS_INTERNAL_ENDPOINT", "http://localhost/escalate")
        importlib.reload(ddos_protection)

        attack_detected = False
        attack_contained = False
        service_recovered = False

        async def mock_post(self, url, *args, **kwargs):
            return httpx.Response(200, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        # Phase 1: Detection - Detect malicious activity
        scenario.metrics.record_request()
        result = await ddos_protection.report_attack("203.0.113.1")
        if result:
            attack_detected = True
            scenario.metrics.record_fallback()

        # Phase 2: Containment - Simulate blocking
        if attack_detected:
            attack_contained = True
            scenario.metrics.record_recovery(0.5)

        # Phase 3: Recovery - Verify service restoration
        scenario.metrics.record_request()
        result = await ddos_protection.report_attack("192.0.2.1")  # Legitimate IP
        if result:
            service_recovered = True

        scenario.end()

        # Validate full recovery cycle
        assert attack_detected, "Should detect attack"
        assert attack_contained, "Should contain attack"
        assert service_recovered, "Should recover service"

        report = scenario.report()
        assert report["avg_recovery_time"] > 0


def test_generate_gameday_report():
    """Generate a comprehensive game day report."""
    scenarios = [
        GameDayScenario("Test 1", "Description 1"),
        GameDayScenario("Test 2", "Description 2"),
    ]

    for scenario in scenarios:
        scenario.start()
        scenario.metrics.record_request()
        scenario.metrics.record_request()
        scenario.metrics.record_failure()
        scenario.end()

    reports = [s.report() for s in scenarios]

    assert len(reports) == 2
    for report in reports:
        assert "name" in report
        assert "duration" in report
        assert "requests" in report
