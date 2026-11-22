"""The Settings page GDPR deletion form can actually pass its CSRF check (#1958)."""

import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bcrypt
import pyotp
from fastapi.testclient import TestClient

from src.admin_ui import admin_ui, auth

TEMPLATE = Path(admin_ui.__file__).resolve().parent / "templates" / "settings.html"


class FakeRedis:
    def hget(self, key, field):
        return None

    def hset(self, key, field, value):
        return 1


class GdprFormCsrfTests(unittest.TestCase):
    def setUp(self):
        os.environ["ADMIN_UI_USERNAME"] = "admin"
        os.environ["ADMIN_UI_PASSWORD_HASH"] = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
        os.environ["ADMIN_UI_ROLE"] = "admin"
        os.environ["ADMIN_UI_2FA_SECRET"] = pyotp.random_base32()
        auth.ADMIN_UI_ROLE = "admin"
        for target, value in (
            ("src.admin_ui.admin_ui.get_redis_connection", FakeRedis()),
            ("src.admin_ui.auth.get_redis_connection", None),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(admin_ui.app)
        self.auth = ("admin", "testpass")

    def _totp(self) -> dict:
        return {"X-2FA-Code": pyotp.TOTP(os.environ["ADMIN_UI_2FA_SECRET"]).now()}

    def test_the_page_renders_the_token_and_the_script_reads_it_from_there(self):
        page = self.client.get("/settings", auth=self.auth, headers=self._totp())
        token = page.cookies.get("csrf_token")
        self.assertTrue(token)
        self.assertIn(f'<meta name="csrf-token" content="{token}">', page.text)
        script = TEMPLATE.read_text()
        self.assertNotIn("document.cookie", script)
        self.assertIn("meta[name=\"csrf-token\"]", script)

    def test_a_deletion_request_with_the_rendered_token_is_accepted(self):
        page = self.client.get("/settings", auth=self.auth, headers=self._totp())
        token = re.search(r'name="csrf-token" content="([^"]+)"', page.text).group(1)
        self.client.cookies.set("csrf_token", page.cookies.get("csrf_token"))
        manager = SimpleNamespace(
            request_data_deletion=lambda user_id, email=None: SimpleNamespace(request_id="req-1")
        )
        with patch("src.shared.gdpr.get_gdpr_manager", return_value=manager):
            response = self.client.post(
                "/gdpr/deletion-request",
                auth=self.auth,
                headers={**self._totp(), "X-CSRF-Token": token},
                data={"user_id": "user_42", "email": ""},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["request_id"], "req-1")

    def test_the_request_is_still_refused_without_a_matching_token(self):
        page = self.client.get("/settings", auth=self.auth, headers=self._totp())
        self.client.cookies.set("csrf_token", page.cookies.get("csrf_token"))
        for headers in ({}, {"X-CSRF-Token": ""}, {"X-CSRF-Token": "not-the-token"}):
            response = self.client.post(
                "/gdpr/deletion-request",
                auth=self.auth,
                headers={**self._totp(), **headers},
                data={"user_id": "user_42"},
            )
            self.assertEqual(response.status_code, 400, headers)
