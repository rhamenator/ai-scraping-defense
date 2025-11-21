"""Tests for vault_client module."""

import os
import unittest
from unittest.mock import MagicMock, Mock, patch

from src.shared.vault_client import (
    VaultClient,
    VaultConfig,
    VaultConnectionError,
    get_vault_client,
)


class TestVaultConfig(unittest.TestCase):
    """Test VaultConfig dataclass."""

    def test_from_env_defaults(self):
        """Test loading config from environment with defaults."""
        with patch.dict(os.environ, {"VAULT_ADDR": "http://test:8200"}, clear=True):
            config = VaultConfig.from_env()
            self.assertEqual(config.addr, "http://test:8200")
            self.assertEqual(config.mount_point, "secret")
            self.assertTrue(config.verify_tls)
            self.assertEqual(config.timeout, 30)

    def test_from_env_custom(self):
        """Test loading config from environment with custom values."""
        env = {
            "VAULT_ADDR": "https://vault.example.com:8200",
            "VAULT_TOKEN": "test-token",
            "VAULT_NAMESPACE": "test-ns",
            "VAULT_MOUNT_POINT": "custom",
            "VAULT_VERIFY_TLS": "false",
            "VAULT_TIMEOUT": "60",
        }
        with patch.dict(os.environ, env, clear=True):
            config = VaultConfig.from_env()
            self.assertEqual(config.addr, "https://vault.example.com:8200")
            self.assertEqual(config.token, "test-token")
            self.assertEqual(config.namespace, "test-ns")
            self.assertEqual(config.mount_point, "custom")
            self.assertFalse(config.verify_tls)
            self.assertEqual(config.timeout, 60)


class TestVaultClient(unittest.TestCase):
    """Test VaultClient class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = VaultConfig(
            addr="http://vault:8200", token="test-token", mount_point="secret"
        )

    @patch("src.shared.vault_client.hvac.Client")
    def test_create_client(self, mock_hvac_client):
        """Test client creation."""
        mock_instance = MagicMock()
        mock_instance.is_authenticated.return_value = True
        mock_hvac_client.return_value = mock_instance

        client = VaultClient(self.config)
        _ = client.client

        mock_hvac_client.assert_called_once_with(
            url=self.config.addr,
            namespace=self.config.namespace,
            verify=self.config.verify_tls,
            timeout=self.config.timeout,
        )

    @patch("src.shared.vault_client.hvac.Client")
    def test_authentication_with_token(self, mock_hvac_client):
        """Test authentication with token."""
        mock_instance = MagicMock()
        mock_instance.is_authenticated.return_value = True
        mock_hvac_client.return_value = mock_instance

        client = VaultClient(self.config)
        self.assertTrue(client.is_authenticated())

    @patch("src.shared.vault_client.hvac.Client")
    def test_authentication_failure(self, mock_hvac_client):
        """Test authentication failure."""
        mock_instance = MagicMock()
        mock_instance.is_authenticated.return_value = False
        mock_hvac_client.return_value = mock_instance

        config = VaultConfig(addr="http://vault:8200")  # No token
        client = VaultClient(config)

        # Expect tenacity.RetryError or VaultConnectionError
        with self.assertRaises((VaultConnectionError, Exception)):
            _ = client.client

    @patch("src.shared.vault_client.hvac.Client")
    def test_read_secret(self, mock_hvac_client):
        """Test reading a secret."""
        mock_instance = MagicMock()
        mock_instance.is_authenticated.return_value = True
        mock_instance.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"key1": "value1", "key2": "value2"}}
        }
        mock_hvac_client.return_value = mock_instance

        client = VaultClient(self.config)
        secret = client.read_secret("myapp/database")

        self.assertIsNotNone(secret)
        self.assertEqual(secret["key1"], "value1")
        self.assertEqual(secret["key2"], "value2")

    @patch("src.shared.vault_client.hvac.Client")
    def test_read_secret_not_found(self, mock_hvac_client):
        """Test reading a non-existent secret."""
        mock_instance = MagicMock()
        mock_instance.is_authenticated.return_value = True
        mock_instance.secrets.kv.v2.read_secret_version.side_effect = __import__(
            "hvac"
        ).exceptions.InvalidPath
        mock_hvac_client.return_value = mock_instance

        client = VaultClient(self.config)
        secret = client.read_secret("nonexistent/path")

        self.assertIsNone(secret)

    @patch("src.shared.vault_client.hvac.Client")
    def test_write_secret(self, mock_hvac_client):
        """Test writing a secret."""
        mock_instance = MagicMock()
        mock_instance.is_authenticated.return_value = True
        mock_hvac_client.return_value = mock_instance

        client = VaultClient(self.config)
        data = {"password": "secret123", "username": "admin"}
        success = client.write_secret("myapp/database", data)

        self.assertTrue(success)
        mock_instance.secrets.kv.v2.create_or_update_secret.assert_called_once()

    @patch("src.shared.vault_client.hvac.Client")
    def test_get_secret_value(self, mock_hvac_client):
        """Test convenience method for getting a single value."""
        mock_instance = MagicMock()
        mock_instance.is_authenticated.return_value = True
        mock_instance.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"password": "secret123"}}
        }
        mock_hvac_client.return_value = mock_instance

        client = VaultClient(self.config)
        value = client.get_secret_value("myapp/database", "password")

        self.assertEqual(value, "secret123")

    @patch("src.shared.vault_client.hvac.Client")
    def test_list_secrets(self, mock_hvac_client):
        """Test listing secrets."""
        mock_instance = MagicMock()
        mock_instance.is_authenticated.return_value = True
        mock_instance.secrets.kv.v2.list_secrets.return_value = {
            "data": {"keys": ["secret1", "secret2", "secret3"]}
        }
        mock_hvac_client.return_value = mock_instance

        client = VaultClient(self.config)
        secrets = client.list_secrets("myapp")

        self.assertEqual(len(secrets), 3)
        self.assertIn("secret1", secrets)

    def test_get_vault_client_no_vault_addr(self):
        """Test that get_vault_client returns None when VAULT_ADDR not set."""
        with patch.dict(os.environ, {}, clear=True):
            client = get_vault_client()
            self.assertIsNone(client)

    @patch("src.shared.vault_client.hvac.Client")
    def test_get_vault_client_authentication_failure(self, mock_hvac_client):
        """Test that get_vault_client returns None when authentication fails."""
        mock_instance = MagicMock()
        mock_instance.is_authenticated.return_value = False
        mock_hvac_client.return_value = mock_instance

        with patch.dict(os.environ, {"VAULT_ADDR": "http://vault:8200"}, clear=True):
            # Should return None when auth fails
            client = get_vault_client()
            self.assertIsNone(client)

    @patch("src.shared.vault_client.hvac.Client")
    def test_get_vault_client_connection_error(self, mock_hvac_client):
        """Test that get_vault_client returns None when connection fails."""
        mock_hvac_client.side_effect = Exception("Connection refused")

        with patch.dict(
            os.environ, {"VAULT_ADDR": "http://vault:8200", "VAULT_TOKEN": "test"}
        ):
            # Should return None and log error
            client = get_vault_client()
            self.assertIsNone(client)

    @patch("src.shared.vault_client.hvac.Client")
    def test_vault_client_read_secret_failure(self, mock_hvac_client):
        """Test that read_secret handles failures gracefully."""
        mock_instance = MagicMock()
        mock_instance.is_authenticated.return_value = True
        mock_instance.secrets.kv.v2.read_secret_version.side_effect = Exception(
            "Network error"
        )
        mock_hvac_client.return_value = mock_instance

        client = VaultClient(self.config)
        secret = client.read_secret("test/path")

        # Should return None on error, not raise
        self.assertIsNone(secret)


if __name__ == "__main__":
    unittest.main()
