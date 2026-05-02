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

    def test_redacts_credentials_from_success_log(self):
        redis_url = "redis://:super-secret@example.com:6380/0"
        mock_client = object()
        with patch.dict(
            redis_client.os.environ,
            {"REDIS_HOST": redis_url},
            clear=False,
        ), patch(
            "src.shared.redis_client._create_client",
            return_value=mock_client,
        ), patch("logging.info") as mock_log:
            conn = redis_client.get_redis_connection()
            self.assertIs(conn, mock_client)
            mock_log.assert_called_once_with(
                "Successfully connected to Redis at redis://example.com:6380 on DB 0"
            )

    def test_redacts_credentials_from_error_log(self):
        redis_url = "redis://:super-secret@example.com:6380/0"
        with patch.dict(
            redis_client.os.environ,
            {"REDIS_HOST": redis_url},
            clear=False,
        ), patch(
            "src.shared.redis_client._create_client",
            side_effect=RuntimeError("boom"),
        ), patch("logging.error") as mock_log:
            conn = redis_client.get_redis_connection()
            self.assertIsNone(conn)
            mock_log.assert_called_once_with(
                "Failed to connect to Redis at redis://example.com:6380 on DB 0: boom"
            )
