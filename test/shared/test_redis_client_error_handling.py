# test/shared/test_redis_client_error_handling.py
import unittest
from unittest.mock import patch

from src.shared import redis_client


class TestRedisClientErrorHandling(unittest.TestCase):
    def test_missing_password_file_fail_fast(self):
        with patch.dict(
            redis_client.os.environ,
            {"REDIS_PASSWORD_FILE": "/no/file"},
        ), patch("builtins.open", side_effect=FileNotFoundError), patch(
            "logging.error"
        ) as mock_log:
            with self.assertRaises(redis_client.RedisConnectionError):
                redis_client.get_redis_connection(fail_fast=True)
            mock_log.assert_called_once_with(
                "Redis password file not found at /no/file"
            )

    def test_connection_error_without_fail_fast(self):
        with patch(
            "src.shared.redis_client._create_client",
            side_effect=redis_client.redis.ConnectionError(),
        ), patch("logging.error") as mock_log:
            conn = redis_client.get_redis_connection()
            self.assertIsNone(conn)
            mock_log.assert_called_once()
