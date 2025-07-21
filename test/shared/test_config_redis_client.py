# test/shared/config_redis_client.test.py
import unittest
from unittest.mock import patch, mock_open, MagicMock
import importlib
import os

from src.shared import config
from src.shared import redis_client


class TestGetSecret(unittest.TestCase):
    def test_secret_file_exists(self):
        with patch.dict(os.environ, {"MY_SECRET_FILE": "/tmp/secret"}), patch(
            "os.path.exists", return_value=True
        ), patch("builtins.open", mock_open(read_data="secret_value")):
            self.assertEqual(config.get_secret("MY_SECRET_FILE"), "secret_value")

    def test_secret_file_missing(self):
        with patch.dict(os.environ, {"MY_SECRET_FILE": "/tmp/missing"}), patch(
            "os.path.exists", return_value=False
        ):
            self.assertIsNone(config.get_secret("MY_SECRET_FILE"))


class TestGetConfig(unittest.TestCase):
    def test_get_config_returns_env_overrides(self):
        env = {"AI_SERVICE_PORT": "1234", "REDIS_PORT": "4321"}
        with patch.dict(os.environ, env, clear=True), patch(
            "src.shared.config.os.path.exists", return_value=False
        ):
            importlib.reload(config)
            cfg = config.get_config()
            self.assertEqual(cfg["AI_SERVICE_PORT"], 1234)
            self.assertEqual(cfg["AI_SERVICE_URL"], "http://ai_service:1234")
            self.assertEqual(cfg["REDIS_PORT"], 4321)
            # ensure all keys are uppercase
            for key in cfg:
                self.assertTrue(key.isupper())


class TestRedisClient(unittest.TestCase):
    def test_missing_password_file_logs_error(self):
        with patch.dict(os.environ, {"REDIS_PASSWORD_FILE": "/no/file"}), patch(
            "builtins.open", side_effect=FileNotFoundError
        ), patch("logging.error") as mock_log, patch("redis.Redis") as mock_redis:
            conn = redis_client.get_redis_connection()
            mock_log.assert_called_once_with(
                "Redis password file not found at /no/file"
            )
            self.assertIsNone(conn)
            mock_redis.assert_not_called()

    def test_authentication_failure_returns_none(self):
        mock_instance = MagicMock()
        mock_instance.ping.side_effect = redis_client.redis.AuthenticationError()
        with patch.dict(os.environ, {"REDIS_PASSWORD_FILE": "/tmp/secret"}), patch(
            "builtins.open", mock_open(read_data="pw")
        ), patch("redis.Redis", return_value=mock_instance) as mock_redis, patch(
            "logging.error"
        ) as mock_log:
            conn = redis_client.get_redis_connection()
            mock_instance.ping.assert_called_once()
            mock_log.assert_called_once_with(
                "Redis authentication failed for DB 0. Check password."
            )
            self.assertIsNone(conn)
            mock_redis.assert_called_once()


if __name__ == "__main__":
    unittest.main()
