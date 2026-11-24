"""Tests for the authenticated Admin UI first-run /setup wizard."""

import os
import secrets
import unittest
from base64 import b64encode
from unittest.mock import patch

import bcrypt
import pyotp
from fastapi.testclient import TestClient

from src.admin_ui import admin_ui, mcp_config, setup_wizard


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        return True

    def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                removed += 1
        return removed

    def incr(self, key):
        val = int(self.store.get(key, 0)) + 1
        self.store[key] = str(val)
        return val

    def expire(self, key, ttl):
        return True

    def ttl(self, key):
        return 3600

    def lpush(self, key, value):
        self.store.setdefault(key, []).insert(0, value)
        return len(self.store[key])

    def ltrim(self, key, start, end):
        items = self.store.get(key, [])
        self.store[key] = items[start : end + 1]
        return True

    def lrange(self, key, start, end):
        items = self.store.get(key, [])
        return items[start:] if end == -1 else items[start : end + 1]

    def hget(self, key, field):
        return self.store.get(key, {}).get(field)

    def hset(self, key, field, value):
        self.store.setdefault(key, {})[field] = value
        return 1

    def hgetall(self, key):
        return dict(self.store.get(key, {}))


class AdminUiSetupWizardTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(admin_ui.app)
        self.password = f"setup-{secrets.token_hex(8)}"
        self.pw_hash = bcrypt.hashpw(self.password.encode(), bcrypt.gensalt()).decode()
        self.totp_secret = pyotp.random_base32()
        self.auth_header = {
            "Authorization": "Basic "
            + b64encode(f"admin:{self.password}".encode()).decode(),
            "X-2FA-Code": pyotp.TOTP(self.totp_secret).now(),
        }
        self.fake_redis = _FakeRedis()
        setup_wizard._FALLBACK_SETUP_STATE.clear()
        mcp_config._FALLBACK_STATE["enable_mcp_model"] = None
        mcp_config._FALLBACK_STATE["servers"] = {}

    def _headers(self):
        return {
            "Authorization": "Basic "
            + b64encode(f"setup_wizard_admin:{self.password}".encode()).decode(),
            "X-2FA-Code": pyotp.TOTP(self.totp_secret).now(),
        }

    def test_setup_requires_auth_and_completes_wizard(self):
        self.assertEqual(self.client.get("/setup").status_code, 401)
        with patch.dict(
            os.environ,
            {
                "ADMIN_UI_USERNAME": "setup_wizard_admin",
                "ADMIN_UI_PASSWORD_HASH": self.pw_hash,
                "ADMIN_UI_2FA_SECRET": self.totp_secret,
            },
            clear=False,
        ), patch("src.admin_ui.setup_wizard.get_redis_connection", return_value=self.fake_redis), patch(
            "src.admin_ui.mcp_config.get_redis_connection", return_value=self.fake_redis
        ), patch("src.admin_ui.auth.get_redis_connection", return_value=self.fake_redis), patch(
            "src.admin_ui.mfa.get_redis_connection", return_value=self.fake_redis
        ), patch(
            "src.admin_ui.admin_ui.get_redis_connection", return_value=self.fake_redis
        ):
            dash_before = self.client.get("/", headers=self._headers())
            self.assertEqual(dash_before.status_code, 200)
            self.assertIn(b"setup-wizard-banner", dash_before.content)

            wizard_get = self.client.get("/setup", headers=self._headers())
            self.assertEqual(wizard_get.status_code, 200)
            csrf = wizard_get.cookies.get("csrf_token")

            wizard_post = self.client.post(
                "/setup",
                headers=self._headers(),
                cookies={"csrf_token": csrf},
                data={
                    "csrf_token": csrf,
                    "real_backend_host": "https://origin.example.com",
                    "model_uri": "mcp://primary/classify",
                    "captcha_provider": "builtin",
                    "cloudflare_enabled": "true",
                    "enable_mcp_model": "true",
                    "mark_complete": "true",
                },
            )
            self.assertEqual(wizard_post.status_code, 200)
            self.assertIn(b"Setup configuration saved.", wizard_post.content)
            self.assertTrue(setup_wizard.is_setup_complete())

            dash_after = self.client.get("/", headers=self._headers())
            self.assertEqual(dash_after.status_code, 200)
            self.assertNotIn(b"setup-wizard-banner", dash_after.content)

    def test_webauthn_register_begin_returns_503_when_unconfigured(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_UI_USERNAME": "setup_wizard_admin",
                "ADMIN_UI_PASSWORD_HASH": self.pw_hash,
                "ADMIN_UI_2FA_SECRET": self.totp_secret,
                "WEBAUTHN_RP_ID": "",
            },
            clear=False,
        ), patch("src.admin_ui.auth.get_redis_connection", return_value=self.fake_redis), patch(
            "src.admin_ui.mfa.get_redis_connection", return_value=self.fake_redis
        ):
            unconfigured = self.client.post("/webauthn/register/begin", headers=self._headers())
            self.assertEqual(unconfigured.status_code, 503)
            self.assertIn("WEBAUTHN_RP_ID", unconfigured.json()["detail"])

    def test_setup_invalid_captcha_is_atomic_and_http_cookie_omits_secure(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_UI_USERNAME": "setup_wizard_admin",
                "ADMIN_UI_PASSWORD_HASH": self.pw_hash,
                "ADMIN_UI_2FA_SECRET": self.totp_secret,
                "REAL_BACKEND_HOST": "https://original.example.com",
                "MODEL_URI": "sklearn:///original.joblib",
                "ENABLE_HTTPS": "false",
            },
            clear=False,
        ), patch("src.admin_ui.setup_wizard.get_redis_connection", return_value=self.fake_redis), patch(
            "src.admin_ui.mcp_config.get_redis_connection", return_value=self.fake_redis
        ), patch("src.admin_ui.auth.get_redis_connection", return_value=self.fake_redis), patch(
            "src.admin_ui.mfa.get_redis_connection", return_value=self.fake_redis
        ), patch("src.admin_ui.admin_ui.get_redis_connection", return_value=self.fake_redis):
            wizard_get = self.client.get("/setup", headers=self._headers())
            self.assertEqual(wizard_get.status_code, 200)
            set_cookie = wizard_get.headers.get("set-cookie", "")
            self.assertNotIn("; secure", set_cookie.lower())
            csrf = wizard_get.cookies.get("csrf_token")
            bad = self.client.post(
                "/setup",
                headers=self._headers(),
                cookies={"csrf_token": csrf},
                data={
                    "csrf_token": csrf,
                    "real_backend_host": "https://changed.example.com",
                    "model_uri": "mcp://changed/model",
                    "captcha_provider": "invalid-provider",
                },
            )
            self.assertEqual(bad.status_code, 400)
            self.assertEqual(os.environ.get("REAL_BACKEND_HOST"), "https://original.example.com")
            self.assertEqual(os.environ.get("MODEL_URI"), "sklearn:///original.joblib")


if __name__ == "__main__":
    unittest.main()
