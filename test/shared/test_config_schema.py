"""Tests for configuration schema validation."""

import secrets
import unittest

from pydantic import ValidationError

from src.shared.config_schema import (
    AppConfig,
    CaptchaConfig,
    Environment,
    EscalationConfig,
    LogLevel,
    PortConfig,
    RedisConfig,
    SecurityConfig,
    ServiceEndpoint,
    TarpitConfig,
)


class TestPortConfig(unittest.TestCase):
    """Test port configuration validation."""

    def test_valid_port(self):
        """Test valid port numbers."""
        port = PortConfig(value=8080)
        self.assertEqual(port.value, 8080)

    def test_port_too_low(self):
        """Test port number below valid range."""
        with self.assertRaises(ValidationError):
            PortConfig(value=0)

    def test_port_too_high(self):
        """Test port number above valid range."""
        with self.assertRaises(ValidationError):
            PortConfig(value=65536)


class TestServiceEndpoint(unittest.TestCase):
    """Test service endpoint configuration."""

    def test_valid_endpoint(self):
        """Test valid service endpoint."""
        endpoint = ServiceEndpoint(host="localhost", port=8000)
        self.assertEqual(endpoint.url, "http://localhost:8000")

    def test_empty_host(self):
        """Test empty host validation."""
        with self.assertRaises(ValidationError):
            ServiceEndpoint(host="", port=8000)


class TestRedisConfig(unittest.TestCase):
    """Test Redis configuration."""

    def test_default_redis_config(self):
        """Test default Redis configuration."""
        config = RedisConfig()
        self.assertEqual(config.host, "redis")
        self.assertEqual(config.port, 6379)
        self.assertEqual(config.db_blocklist, 2)

    def test_redis_with_password(self):
        """Test Redis configuration with password masking."""
        password = secrets.token_urlsafe(12)
        config = RedisConfig(password=password)
        # Password should be accessible as-is for actual use
        self.assertEqual(config.password, password)
        # But should be masked in repr
        repr_str = repr(config)
        self.assertIn("***MASKED***", repr_str)
        self.assertNotIn(password, repr_str)


class TestTarpitConfig(unittest.TestCase):
    """Test tarpit configuration validation."""

    def test_valid_tarpit_config(self):
        """Test valid tarpit configuration."""
        config = TarpitConfig(min_delay_sec=0.5, max_delay_sec=1.5)
        self.assertEqual(config.min_delay_sec, 0.5)
        self.assertEqual(config.max_delay_sec, 1.5)
        self.assertEqual(config.max_stream_seconds, 60.0)

    def test_invalid_delay_range(self):
        """Test tarpit with min_delay > max_delay."""
        with self.assertRaises(ValidationError):
            TarpitConfig(min_delay_sec=2.0, max_delay_sec=1.0)

    def test_delay_bounds(self):
        """Test tarpit delay bounds."""
        with self.assertRaises(ValidationError):
            TarpitConfig(min_delay_sec=-1.0)

        with self.assertRaises(ValidationError):
            TarpitConfig(max_delay_sec=20.0)

    def test_max_stream_seconds_bounds(self):
        """Test tarpit stream hard-limit bounds."""
        with self.assertRaises(ValidationError):
            TarpitConfig(max_stream_seconds=0.0)

        with self.assertRaises(ValidationError):
            TarpitConfig(max_stream_seconds=3601.0)


class TestEscalationConfig(unittest.TestCase):
    """Test escalation configuration."""

    def test_valid_webhook_url(self):
        """Test valid webhook URL."""
        config = EscalationConfig(webhook_url="https://example.com/webhook")
        self.assertEqual(config.webhook_url, "https://example.com/webhook")

    def test_invalid_webhook_url(self):
        """Test invalid webhook URL."""
        with self.assertRaises(ValidationError):
            EscalationConfig(webhook_url="not-a-url")

    def test_threshold_bounds(self):
        """Test threshold validation."""
        config = EscalationConfig(threshold=0.8)
        self.assertEqual(config.threshold, 0.8)

        with self.assertRaises(ValidationError):
            EscalationConfig(threshold=1.5)


class TestCaptchaConfig(unittest.TestCase):
    """Test CAPTCHA configuration."""

    def test_valid_captcha_config(self):
        """Test valid CAPTCHA configuration."""
        config = CaptchaConfig(score_threshold_low=0.2, score_threshold_high=0.5)
        self.assertEqual(config.score_threshold_low, 0.2)
        self.assertEqual(config.score_threshold_high, 0.5)

    def test_invalid_threshold_order(self):
        """Test CAPTCHA with low > high threshold."""
        with self.assertRaises(ValidationError):
            CaptchaConfig(score_threshold_low=0.7, score_threshold_high=0.3)


class TestSecurityConfig(unittest.TestCase):
    """Test security configuration."""

    def test_https_without_certs(self):
        """Test HTTPS enabled without certificate paths."""
        with self.assertRaises(ValidationError):
            SecurityConfig(enable_https=True)

    def test_https_with_certs(self):
        """Test HTTPS enabled with certificate paths."""
        config = SecurityConfig(
            enable_https=True,
            tls_cert_path="/path/to/cert",
            tls_key_path="/path/to/key",
        )
        self.assertTrue(config.enable_https)
        self.assertEqual(config.tls_cert_path, "/path/to/cert")


class TestAppConfig(unittest.TestCase):
    """Test complete application configuration."""

    def test_minimal_app_config(self):
        """Test minimal valid application configuration."""
        config = AppConfig(
            model_uri="sklearn:///app/models/bot_detection_rf_model.joblib"
        )
        self.assertEqual(config.log_level, LogLevel.INFO)
        self.assertEqual(config.app_env, Environment.PRODUCTION)
        self.assertEqual(config.tenant_id, "default")

    def test_app_config_to_dict(self):
        """Test configuration export to dictionary."""
        config = AppConfig(
            model_uri="sklearn:///model.joblib",
            tenant_id="test-tenant",
        )
        config_dict = config.to_dict()
        self.assertIsInstance(config_dict, dict)
        self.assertEqual(config_dict["tenant_id"], "test-tenant")
        self.assertIn("metadata", config_dict)


if __name__ == "__main__":
    unittest.main()
