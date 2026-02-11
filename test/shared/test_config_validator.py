"""Tests for configuration validation and loading."""

import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.shared.config_schema import AppConfig, Environment
from src.shared.config_validator import ConfigLoader, ConfigValidationError


class TestConfigLoader(unittest.TestCase):
    """Test configuration loading from environment."""

    def setUp(self):
        """Set up test fixtures."""
        self.minimal_env = {
            "MODEL_URI": "sklearn:///app/models/bot_detection_rf_model.joblib",
            "AI_SERVICE_PORT": "8000",
            "ESCALATION_ENGINE_PORT": "8003",
            "TARPIT_API_PORT": "8001",
            "ADMIN_UI_PORT": "5002",
        }

    def test_load_minimal_config(self):
        """Test loading minimal valid configuration."""
        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(self.minimal_env)

        self.assertIsInstance(config, AppConfig)
        self.assertEqual(
            config.model_uri, "sklearn:///app/models/bot_detection_rf_model.joblib"
        )
        self.assertEqual(config.ai_service.port, 8000)

    def test_load_with_all_features(self):
        """Test loading configuration with all features enabled."""
        env = self.minimal_env.copy()
        env.update(
            {
                "LOG_LEVEL": "DEBUG",
                "DEBUG": "true",
                "TENANT_ID": "test-tenant",
                "APP_ENV": "development",
                "REDIS_HOST": "localhost",
                "REDIS_PORT": "6380",
                "TAR_PIT_MIN_DELAY_SEC": "0.5",
                "TAR_PIT_MAX_DELAY_SEC": "2.0",
                "TAR_PIT_MAX_STREAM_SECONDS": "45.0",
                "ESCALATION_THRESHOLD": "0.9",
                "ENABLE_TARPIT_CATCH_ALL": "true",
                "ENABLE_FINGERPRINTING": "true",
            }
        )

        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env)

        self.assertEqual(config.tenant_id, "test-tenant")
        self.assertEqual(config.app_env, Environment.DEVELOPMENT)
        self.assertTrue(config.debug)
        self.assertEqual(config.redis.port, 6380)
        self.assertEqual(config.tarpit.min_delay_sec, 0.5)
        self.assertEqual(config.tarpit.max_stream_seconds, 45.0)
        self.assertEqual(config.escalation.threshold, 0.9)

    def test_validate_slack_alerts_accepts_webhook_file(self):
        env = self.minimal_env.copy()
        env.update(
            {
                "ALERT_METHOD": "slack",
                "APP_ENV": "testing",
                "ENABLE_EXTERNAL_API_CLASSIFICATION": "false",
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            webhook_file = Path(tmpdir) / "slack_webhook.txt"
            webhook_file.write_text("https://example.invalid/webhook", encoding="utf-8")

            loader = ConfigLoader(strict=True)
            config = loader.load_from_env(env)
            with patch.dict(
                os.environ,
                {
                    "ALERT_SLACK_WEBHOOK_URL_FILE": str(webhook_file),
                    "ENABLE_EXTERNAL_API_CLASSIFICATION": "false",
                },
            ):
                ok, errors = loader.validate_config(config)

        self.assertTrue(ok, f"Expected config to be valid, got errors={errors}")

    def test_validate_webhook_alerts_accepts_webhook_file(self):
        env = self.minimal_env.copy()
        env.update(
            {
                "ALERT_METHOD": "webhook",
                "APP_ENV": "testing",
                "ENABLE_EXTERNAL_API_CLASSIFICATION": "false",
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            webhook_file = Path(tmpdir) / "generic_webhook.txt"
            webhook_file.write_text("https://example.invalid/webhook", encoding="utf-8")

            loader = ConfigLoader(strict=True)
            config = loader.load_from_env(env)
            with patch.dict(
                os.environ,
                {
                    "ALERT_GENERIC_WEBHOOK_URL_FILE": str(webhook_file),
                    "ENABLE_EXTERNAL_API_CLASSIFICATION": "false",
                },
            ):
                ok, errors = loader.validate_config(config)

        self.assertTrue(ok, f"Expected config to be valid, got errors={errors}")

    def test_load_with_secrets(self):
        """Test loading configuration with secret files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create secret files
            redis_secret = Path(tmpdir) / "redis_password"
            redis_secret.write_text("redis_secret_123")

            pg_secret = Path(tmpdir) / "pg_password"
            pg_secret.write_text("postgres_secret_456")

            env = self.minimal_env.copy()
            env.update(
                {
                    "REDIS_PASSWORD_FILE": str(redis_secret),
                    "PG_PASSWORD_FILE": str(pg_secret),
                }
            )

            loader = ConfigLoader(strict=False)
            config = loader.load_from_env(env)

            # Passwords should be loaded (accessible for use)
            self.assertEqual(config.redis.password, "redis_secret_123")
            self.assertEqual(config.postgres.password, "postgres_secret_456")

            # But should be masked in repr
            repr_str = repr(config.redis)
            self.assertIn("***MASKED***", repr_str)
            self.assertNotIn("redis_secret_123", repr_str)

    def test_strict_mode_with_invalid_config(self):
        """Test strict mode raises error on invalid configuration."""
        # Use empty MODEL_URI which violates min_length=1 constraint
        env = {"MODEL_URI": ""}

        loader = ConfigLoader(strict=True)
        # Should raise error due to validation failure
        with self.assertRaises(ConfigValidationError):
            loader.load_from_env(env)

    def test_non_strict_mode_with_invalid_config(self):
        """Test non-strict mode returns minimal config on error."""
        env = {"INVALID_KEY": "value"}

        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env)

        # Should return minimal valid config
        self.assertIsInstance(config, AppConfig)

    def test_validate_production_config(self):
        """Test production configuration validation."""
        env = self.minimal_env.copy()
        env.update(
            {
                "APP_ENV": "production",
                "DEBUG": "true",  # Should be false in production
            }
        )

        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env)

        is_valid, errors = loader.validate_config(config)

        self.assertFalse(is_valid)
        self.assertTrue(
            any("DEBUG mode should not be enabled in production" in e for e in errors)
        )

    def test_validate_admin_ui_password_hash_required(self):
        """Test production requires a password hash."""
        env = self.minimal_env.copy()
        env.update({"APP_ENV": "production", "DEBUG": "false"})

        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env)

        is_valid, errors = loader.validate_config(config)

        self.assertFalse(is_valid)
        self.assertTrue(any("ADMIN_UI_PASSWORD_HASH must be set" in e for e in errors))

    def test_validate_admin_ui_password_hash_format(self):
        """Test password hash must be bcrypt formatted."""
        env = self.minimal_env.copy()
        env.update(
            {
                "APP_ENV": "production",
                "DEBUG": "false",
                "ADMIN_UI_PASSWORD_HASH": "not-a-hash",
            }
        )

        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env)

        is_valid, errors = loader.validate_config(config)

        self.assertFalse(is_valid)
        self.assertTrue(any("must be a bcrypt hash" in e for e in errors))

    def test_validate_admin_ui_password_hash_cost(self):
        """Test bcrypt cost must meet minimum."""
        env = self.minimal_env.copy()
        env.update(
            {
                "APP_ENV": "production",
                "DEBUG": "false",
                "ADMIN_UI_PASSWORD_HASH": "$2b$08$" + "." * 53,
            }
        )

        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env)

        is_valid, errors = loader.validate_config(config)

        self.assertFalse(is_valid)
        self.assertTrue(any("bcrypt cost must be >= 12" in e for e in errors))

    def test_validate_model_provider_keys(self):
        """Test validation of model provider API keys."""
        env = self.minimal_env.copy()
        env["MODEL_URI"] = "openai://gpt-4"

        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env)

        # Should require OPENAI_API_KEY
        with patch.dict(os.environ, {}, clear=True):
            is_valid, errors = loader.validate_config(config)
            self.assertFalse(is_valid)
            self.assertTrue(any("OPENAI_API_KEY" in e for e in errors))

    def test_validate_captcha_config(self):
        """Test CAPTCHA configuration validation."""
        env = self.minimal_env.copy()
        env["ENABLE_CAPTCHA_TRIGGER"] = "true"

        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env)

        is_valid, errors = loader.validate_config(config)

        # Should require CAPTCHA_VERIFICATION_URL and CAPTCHA_SECRET
        self.assertFalse(is_valid)
        self.assertTrue(any("CAPTCHA_VERIFICATION_URL" in e for e in errors))
        self.assertTrue(any("CAPTCHA_SECRET" in e for e in errors))

    def test_validate_jwt_algorithm_values(self):
        """Test JWT algorithm validation rejects unsupported values."""
        env = self.minimal_env.copy()
        env["AUTH_JWT_ALGORITHMS"] = "none"

        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env)

        with patch.dict(os.environ, {"AUTH_JWT_ALGORITHMS": "none"}, clear=False):
            is_valid, errors = loader.validate_config(config)

        self.assertFalse(is_valid)
        self.assertTrue(
            any("AUTH_JWT_ALGORITHMS contains unsupported values" in e for e in errors)
        )

    def test_validate_jwt_secret_min_length(self):
        """Test JWT secret must meet minimum length."""
        env = self.minimal_env.copy()
        env["AUTH_JWT_SECRET"] = secrets.token_urlsafe(4)

        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env)

        is_valid, errors = loader.validate_config(config)

        self.assertFalse(is_valid)
        self.assertTrue(
            any("AUTH_JWT_SECRET must be at least 32 characters" in e for e in errors)
        )

    def test_validate_external_api_requires_url(self):
        """Test external API requires a URL when enabled."""
        env = self.minimal_env.copy()

        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env)

        with patch.dict(
            os.environ, {"ENABLE_EXTERNAL_API_CLASSIFICATION": "true"}, clear=False
        ):
            is_valid, errors = loader.validate_config(config)

        self.assertFalse(is_valid)
        self.assertTrue(any("EXTERNAL_API_URL required" in e for e in errors))

    def test_validate_external_api_requires_https(self):
        """Test external API URL requires https by default."""
        env = self.minimal_env.copy()

        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env)

        with patch.dict(
            os.environ,
            {
                "ENABLE_EXTERNAL_API_CLASSIFICATION": "true",
                "EXTERNAL_API_URL": "http://example.com",
            },
            clear=False,
        ):
            is_valid, errors = loader.validate_config(config)

        self.assertFalse(is_valid)
        self.assertTrue(any("EXTERNAL_API_URL must use https://" in e for e in errors))

    def test_validate_ip_reputation_requires_url(self):
        """Test IP reputation requires a URL when enabled."""
        env = self.minimal_env.copy()

        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env)

        with patch.dict(os.environ, {"ENABLE_IP_REPUTATION": "true"}, clear=False):
            is_valid, errors = loader.validate_config(config)

        self.assertFalse(is_valid)
        self.assertTrue(any("IP_REPUTATION_API_URL required" in e for e in errors))

    def test_validate_ip_reputation_requires_https(self):
        """Test IP reputation URL requires https by default."""
        env = self.minimal_env.copy()

        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env)

        with patch.dict(
            os.environ,
            {"IP_REPUTATION_API_URL": "http://example.com"},
            clear=False,
        ):
            is_valid, errors = loader.validate_config(config)

        self.assertFalse(is_valid)
        self.assertTrue(
            any("IP_REPUTATION_API_URL must use https://" in e for e in errors)
        )

    def test_compute_checksum(self):
        """Test configuration checksum computation."""
        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(self.minimal_env)

        checksum1 = loader.compute_checksum(config)
        checksum2 = loader.compute_checksum(config)

        # Same config should produce same checksum
        self.assertEqual(checksum1, checksum2)

        # Different config should produce different checksum
        env2 = self.minimal_env.copy()
        env2["TENANT_ID"] = "different-tenant"
        config2 = loader.load_from_env(env2)
        checksum3 = loader.compute_checksum(config2)

        self.assertNotEqual(checksum1, checksum3)


if __name__ == "__main__":
    unittest.main()
