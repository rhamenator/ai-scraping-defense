import base64
import json
import os
import time
import unittest
from unittest.mock import MagicMock, patch

from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.admin_ui import admin_ui, auth, passkeys


class TestPasskeyEncryption(unittest.TestCase):
    def setUp(self):
        key = base64.b64encode(b"1" * 32).decode()
        patcher = patch.dict(os.environ, {"PASSKEYS_ENC_KEY": key})
        patcher.start()
        self.addCleanup(patcher.stop)
        passkeys._ENC_KEY = None

    def test_encrypt_decrypt_round_trip(self):
        data = {"a": 1}
        encrypted = passkeys.encrypt_json(data)
        json_str = json.dumps(data, **passkeys.JSON_SERIALIZATION_PARAMS)
        self.assertNotIn(json_str, encrypted)
        decrypted = passkeys.decrypt_json(encrypted)
        self.assertEqual(decrypted, data)

    def test_decrypt_invalid_input(self):
        with self.assertRaises(Exception):
            passkeys.decrypt_json("invalid")


class TestCredentialStorage(unittest.TestCase):
    def setUp(self):
        key = base64.b64encode(b"2" * 32).decode()
        patcher = patch.dict(os.environ, {"PASSKEYS_ENC_KEY": key})
        patcher.start()
        self.addCleanup(patcher.stop)
        passkeys._ENC_KEY = None

    def test_store_and_load_credential(self):
        mock_redis = MagicMock()
        cred = {"credential_id": "id", "public_key": "pk", "sign_count": 1}
        with patch(
            "src.admin_ui.passkeys.get_redis_connection", return_value=mock_redis
        ):
            passkeys._store_credential("user", cred)
            stored = mock_redis.set.call_args[0][1]
            self.assertNotIn("public_key", stored)
            mock_redis.get.return_value = stored
            self.assertEqual(passkeys._load_credential("user"), cred)
            mock_redis.get.return_value = json.dumps(cred)
            with patch("src.admin_ui.passkeys.logger") as mock_logger:
                self.assertEqual(passkeys._load_credential("user"), cred)
                mock_logger.warning.assert_called_once()


class TestPasskeyToken(unittest.TestCase):
    def test_store_passkey_token_validations(self):
        mock_redis = MagicMock()
        with patch(
            "src.admin_ui.passkeys.get_redis_connection", return_value=mock_redis
        ):
            past = time.time() - 1
            with self.assertRaises(ValueError):
                passkeys._store_passkey_token("tok", "user", exp=past)
            near_future = time.time() + 0.2
            passkeys._store_passkey_token("tok", "user", exp=near_future)
            self.assertGreaterEqual(mock_redis.set.call_args[1]["ex"], 1)
            mock_redis.set.reset_mock()
            with patch("src.admin_ui.passkeys.time.time", return_value=1000):
                passkeys._store_passkey_token("tok", "user")
                self.assertEqual(
                    mock_redis.set.call_args[1]["ex"], passkeys.PASSKEY_TOKEN_TTL
                )


class TestPasskeyEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(admin_ui.app)
        admin_ui.app.dependency_overrides[auth.require_auth] = lambda: "admin"
        self.addCleanup(
            lambda: admin_ui.app.dependency_overrides.pop(auth.require_auth, None)
        )

    def test_login_requires_username(self):
        resp = self.client.post("/passkey/login", json={})
        self.assertEqual(resp.status_code, 422)

    def test_login_invalid_body(self):
        resp = self.client.post("/passkey/login", json="bad")
        self.assertEqual(resp.status_code, 422)

    def test_login_begin(self):
        with patch(
            "src.admin_ui.auth.passkeys.begin_login", return_value=JSONResponse({})
        ) as mock_begin:
            resp = self.client.post("/passkey/login", json={"username": "u"})
            self.assertEqual(resp.status_code, 200)
            mock_begin.assert_called_once_with("u")

    def test_login_begin_rejects_long_username(self):
        resp = self.client.post("/passkey/login", json={"username": "a" * 200})
        self.assertEqual(resp.status_code, 400)

    def test_login_complete(self):
        with patch(
            "src.admin_ui.auth.passkeys.complete_login",
            return_value=JSONResponse({"token": "t"}),
        ) as mock_complete:
            payload = {"username": "u", "credential": {}}
            resp = self.client.post("/passkey/login", json=payload)
            self.assertEqual(resp.status_code, 200)
            mock_complete.assert_called_once_with(payload)

    def test_register_invalid_body(self):
        resp = self.client.post("/passkey/register", json="bad")
        self.assertEqual(resp.status_code, 422)

    def test_register_begin(self):
        with patch(
            "src.admin_ui.auth.passkeys.begin_registration",
            return_value=JSONResponse({}),
        ) as mock_begin:
            resp = self.client.post("/passkey/register", json={})
            self.assertEqual(resp.status_code, 200)
            mock_begin.assert_called_once_with("admin")

    def test_register_complete(self):
        with patch(
            "src.admin_ui.auth.passkeys.complete_registration",
            return_value=JSONResponse({"status": "ok"}),
        ) as mock_complete:
            resp = self.client.post("/passkey/register", json={"credential": {}})
            self.assertEqual(resp.status_code, 200)
            mock_complete.assert_called_once()
