# test/admin_ui/test_webauthn.py
import base64
import time
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from src.admin_ui import webauthn


class TestWebAuthnFlows(unittest.TestCase):
    def test_validate_username_rejects_long_value(self):
        with self.assertRaises(HTTPException):
            webauthn._validate_username("a" * 200, detail="Invalid login request")

    def test_store_and_consume_challenge(self):
        mock_redis = MagicMock()
        with patch(
            "src.admin_ui.webauthn.get_redis_connection", return_value=mock_redis
        ):
            webauthn._store_webauthn_challenge("user", b"abc")
            mock_redis.set.assert_called_once()
        mock_redis.getdel.return_value = base64.b64encode(b"abc")
        with patch(
            "src.admin_ui.webauthn.get_redis_connection", return_value=mock_redis
        ):
            result = webauthn._consume_webauthn_challenge("user")
        self.assertEqual(result, b"abc")

    def test_store_and_consume_token(self):
        mock_redis = MagicMock()
        future = time.time() + 10
        with patch(
            "src.admin_ui.webauthn.get_redis_connection", return_value=mock_redis
        ):
            webauthn._store_webauthn_token("tok", "user", exp=future)
            args, kwargs = mock_redis.set.call_args
            self.assertEqual(args[0], webauthn._token_key("tok"))
            self.assertEqual(args[1], "user")
            self.assertGreater(kwargs["ex"], 0)
        mock_redis.getdel.return_value = "user"
        with patch(
            "src.admin_ui.webauthn.get_redis_connection", return_value=mock_redis
        ):
            self.assertEqual(webauthn._consume_webauthn_token("tok"), "user")

    def test_has_webauthn_tokens(self):
        mock_redis = MagicMock()
        mock_redis.scan_iter.return_value = iter(["token"])
        with patch(
            "src.admin_ui.webauthn.get_redis_connection", return_value=mock_redis
        ):
            self.assertTrue(webauthn._has_webauthn_tokens())
        mock_redis.scan_iter.return_value = iter([])
        with patch(
            "src.admin_ui.webauthn.get_redis_connection", return_value=mock_redis
        ):
            self.assertFalse(webauthn._has_webauthn_tokens())
