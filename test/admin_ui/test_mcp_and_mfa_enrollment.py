"""Tests for Admin UI MCP server management, TOTP QR enrollment, and password change."""

import os
import secrets
import unittest
from base64 import b64encode
from unittest.mock import patch

import bcrypt
import pyotp
from fastapi.testclient import TestClient

from src.admin_ui import admin_ui, mcp_config
from src.shared.mcp_client import load_server_config


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


class AdminUiMcpAndMfaTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(admin_ui.app)
        self.password = f"init-{secrets.token_hex(8)}"
        self.pw_hash = bcrypt.hashpw(self.password.encode(), bcrypt.gensalt()).decode()
        self.totp_secret = pyotp.random_base32()
        self.auth_header = {
            "Authorization": "Basic "
            + b64encode(f"admin:{self.password}".encode()).decode(),
            "X-2FA-Code": pyotp.TOTP(self.totp_secret).now(),
        }
        self.fake_redis = _FakeRedis()
        mcp_config._FALLBACK_STATE["enable_mcp_model"] = None
        mcp_config._FALLBACK_STATE["servers"] = {}
        mcp_config._FALLBACK_TOKENS.clear()

    def _csrf(self):
        resp = self.client.get("/mcp", headers=self.auth_header)
        self.assertEqual(resp.status_code, 200)
        csrf_cookie = resp.cookies.get("csrf_token")
        return csrf_cookie

    def _post_mcp(self, csrf: str, data: dict):
        return self.client.post(
            "/mcp",
            headers=self.auth_header,
            cookies={"csrf_token": csrf},
            data={"csrf_token": csrf, **data},
        )

    def test_mcp_page_upsert_toggle_and_remove_without_exposing_token(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_UI_USERNAME": "admin",
                "ADMIN_UI_PASSWORD_HASH": self.pw_hash,
                "ADMIN_UI_2FA_SECRET": self.totp_secret,
            },
            clear=False,
        ), patch("src.admin_ui.mcp_config.get_redis_connection", return_value=self.fake_redis), patch(
            "src.admin_ui.auth.get_redis_connection", return_value=self.fake_redis
        ):
            csrf = self._csrf()
            secret_tok = f"tok-{secrets.token_hex(8)}"
            upsert = self._post_mcp(
                csrf,
                {
                    "action": "upsert_server",
                    "server_name": "PRIMARY",
                    "transport": "ws",
                    "url": "ws://mcp-primary.internal:9001/mcp",
                    "timeout": "45",
                    "auth_token": secret_tok,
                },
            )
            self.assertEqual(upsert.status_code, 200)
            self.assertIn(b"PRIMARY", upsert.content)
            self.assertIn(b"Configured", upsert.content)
            self.assertNotIn(secret_tok.encode(), upsert.content)

            removed = self._post_mcp(
                csrf, {"action": "remove_server", "server_name": "PRIMARY"}
            )
            self.assertEqual(removed.status_code, 200)
            self.assertIn(b"No MCP servers configured.", removed.content)
            self.assertNotIn(b"ws://mcp-primary.internal:9001/mcp", removed.content)

    def test_mcp_stdio_and_persisted_token_load_in_client(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_UI_USERNAME": "admin",
                "ADMIN_UI_PASSWORD_HASH": self.pw_hash,
                "ADMIN_UI_2FA_SECRET": self.totp_secret,
            },
            clear=False,
        ), patch("src.admin_ui.mcp_config.get_redis_connection", return_value=self.fake_redis), patch(
            "src.admin_ui.auth.get_redis_connection", return_value=self.fake_redis
        ):
            csrf = self._csrf()
            secret_tok = f"tok-{secrets.token_hex(8)}"
            self.assertEqual(
                self._post_mcp(
                    csrf,
                    {
                        "action": "upsert_server",
                        "server_name": "WS_PERSIST",
                        "transport": "ws",
                        "url": "wss://mcp.internal:9443/mcp",
                        "timeout": "30",
                        "auth_token": secret_tok,
                    },
                ).status_code,
                200,
            )
            self.assertEqual(
                self._post_mcp(
                    csrf,
                    {
                        "action": "upsert_server",
                        "server_name": "STDIO_SRV",
                        "transport": "stdio",
                        "url": "python -m my_mcp_server --port 9000",
                        "timeout": "20",
                        "auth_token": "",
                    },
                ).status_code,
                200,
            )
            with patch("src.shared.redis_client.get_redis_connection", return_value=self.fake_redis):
                ws_cfg = load_server_config("WS_PERSIST")
                self.assertEqual(ws_cfg.headers.get("Authorization"), f"Bearer {secret_tok}")
                stdio_cfg = load_server_config("STDIO_SRV")
                self.assertEqual(stdio_cfg.executable, "python")
                self.assertEqual(stdio_cfg.args, ["-m", "my_mcp_server", "--port", "9000"])

    def test_totp_setup_and_verify_enrollment(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_UI_USERNAME": "admin",
                "ADMIN_UI_PASSWORD_HASH": self.pw_hash,
                "ADMIN_UI_2FA_SECRET": self.totp_secret,
            },
            clear=False,
        ), patch("src.admin_ui.mfa.get_redis_connection", return_value=self.fake_redis), patch(
            "src.admin_ui.auth.get_redis_connection", return_value=self.fake_redis
        ):
            csrf = self._csrf()
            setup = self.client.post(
                "/mfa/totp/setup",
                headers={**self.auth_header, "X-CSRF-Token": csrf},
                cookies={"csrf_token": csrf},
            )
            self.assertEqual(setup.status_code, 200)
            data = setup.json()
            self.assertIn("secret", data)
            self.assertIn("otpauth://totp/", data["otpauth_uri"])
            self.assertIsInstance(data["qr_matrix"], list)

            bad = self.client.post(
                "/mfa/totp/verify",
                headers={**self.auth_header, "X-CSRF-Token": csrf},
                cookies={"csrf_token": csrf},
                json={"code": "000000"},
            )
            self.assertEqual(bad.status_code, 400)

            good_code = pyotp.TOTP(data["secret"]).now()
            good = self.client.post(
                "/mfa/totp/verify",
                headers={**self.auth_header, "X-CSRF-Token": csrf},
                cookies={"csrf_token": csrf},
                json={"code": good_code},
            )
            self.assertEqual(good.status_code, 200)
            self.assertTrue(good.json()["totp_enabled"])

            fresh_client = TestClient(admin_ui.app)
            enrolled_auth = {
                "Authorization": self.auth_header["Authorization"],
                "X-2FA-Code": pyotp.TOTP(data["secret"]).now(),
            }
            self.assertEqual(fresh_client.get("/mcp", headers=enrolled_auth).status_code, 200)

    def test_change_password_updates_active_hash(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_UI_USERNAME": "admin",
                "ADMIN_UI_PASSWORD_HASH": self.pw_hash,
                "ADMIN_UI_2FA_SECRET": self.totp_secret,
            },
            clear=False,
        ), patch("src.admin_ui.auth.get_redis_connection", return_value=self.fake_redis):
            csrf = self._csrf()
            new_pw = f"new-{secrets.token_hex(8)}"
            resp = self.client.post(
                "/account/password",
                headers={**self.auth_header, "X-CSRF-Token": csrf},
                cookies={"csrf_token": csrf},
                json={
                    "current_password": self.password,
                    "new_password": new_pw,
                    "confirm_password": new_pw,
                },
            )
            self.assertEqual(resp.status_code, 200)
            new_auth = {
                "Authorization": "Basic " + b64encode(f"admin:{new_pw}".encode()).decode(),
                "X-2FA-Code": pyotp.TOTP(self.totp_secret).now(),
            }
            check = self.client.get("/mcp", headers=new_auth)
            self.assertEqual(check.status_code, 200)


if __name__ == "__main__":
    unittest.main()
