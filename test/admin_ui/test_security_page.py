"""The admin Security page and CSRF-protected backup code regeneration (#1952)."""

import os
import secrets
import unittest
from pathlib import Path
from unittest.mock import patch

import bcrypt
import pyotp
from fastapi.testclient import TestClient

from src.admin_ui import admin_ui, auth, mfa, passkeys
from test.admin_ui.test_mfa_backup_codes import MockRedis

STATIC = Path(admin_ui.__file__).resolve().parent / "static"


class SecurityPageTests(unittest.TestCase):
    def setUp(self):
        os.environ["ADMIN_UI_USERNAME"] = "admin"
        os.environ["ADMIN_UI_PASSWORD_HASH"] = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
        os.environ["ADMIN_UI_ROLE"] = "admin"
        os.environ["ADMIN_UI_2FA_SECRET"] = pyotp.random_base32()
        auth.ADMIN_UI_ROLE = "admin"
        self.redis = MockRedis()
        for target in ("src.admin_ui.auth.get_redis_connection", "src.admin_ui.mfa.get_redis_connection"):
            patcher = patch(target, return_value=self.redis)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(admin_ui.app)
        self.auth = ("admin", "testpass")

    def _totp(self) -> dict:
        return {"X-2FA-Code": pyotp.TOTP(os.environ["ADMIN_UI_2FA_SECRET"]).now()}

    def _page(self):
        return self.client.get("/security", auth=self.auth, headers=self._totp())

    def test_page_shows_identity_method_and_factor_status(self):
        with patch.object(passkeys, "_load_credential", return_value=None):
            html = self._page().text
        self.assertIn('id="sec-user">admin<', html)
        self.assertIn("Username and password", html)
        self.assertIn("Not enrolled", html)
        self.assertIn("Set up for this deployment", html)
        self.assertIn("None generated", html)

    def test_page_reports_an_enrolled_passkey_and_the_backup_code_count(self):
        codes = mfa.generate_backup_codes(count=3)
        self.assertTrue(mfa.store_backup_codes("admin", codes))
        with patch.object(passkeys, "_load_credential", return_value={"credential_id": b"x"}):
            html = self._page().text
        self.assertIn("Enrolled", html)
        self.assertIn("3 of 3 remaining", html)
        self.assertIn("generated 20", html)  # the year prefix of the generated-at time

    def test_page_never_contains_backup_codes_or_their_hashes(self):
        codes = mfa.generate_backup_codes(count=3)
        mfa.store_backup_codes("admin", codes)
        stored = self.redis.get(mfa._backup_codes_key("admin"))
        page = self._page()
        for code in codes:
            self.assertNotIn(code, page.text)
        self.assertNotIn("$2b$", page.text)
        self.assertEqual(page.headers["cache-control"], "no-store")
        self.assertTrue(stored)

    def test_page_sets_the_csrf_cookie_and_renders_the_token(self):
        page = self._page()
        token = page.cookies.get("csrf_token")
        self.assertTrue(token)
        self.assertIn(f'<meta name="csrf-token" content="{token}">', page.text)

    def test_sso_users_get_a_note_instead_of_a_sign_out_button(self):
        """Signing out locally would just be undone by the provider or proxy, so the button is not offered."""
        plain = self._page().text
        self.assertIn('id="sign-out"', plain)
        self.assertNotIn("sso-signout-note", plain)
        with patch.object(admin_ui, "_security_page_context") as context:
            context.return_value = {
                "user": "admin",
                "method": "Single sign-on (SAML)",
                "sso": True,
                "passkey_enrolled": False,
                "totp_enabled": False,
                "backup": {"remaining": 0, "total": 0, "created_at": None, "created_text": None},
            }
            sso = self._page().text
        self.assertIn('id="sso-signout-note"', sso)
        self.assertIn("sign out through your provider", sso)
        self.assertNotIn('id="sign-out"', sso)

    def test_context_marks_oidc_and_saml_as_sso(self):
        for provider, expected in (("oidc", True), ("saml", True), ("basic", False)):
            request = type("R", (), {})()
            request.state = type("S", (), {"admin_ui_auth_provider": provider})()
            request.cookies = {}
            with patch.object(passkeys, "_load_credential", return_value=None):
                context = admin_ui._security_page_context(request, "admin")
            self.assertEqual(context["sso"], expected, provider)

    def test_a_passkey_store_failure_does_not_break_the_page(self):
        with patch.object(passkeys, "_load_credential", side_effect=RuntimeError("boom")):
            self.assertEqual(self._page().status_code, 200)

    def test_page_is_admin_only_and_needs_authentication(self):
        self.assertEqual(self.client.get("/security").status_code, 401)
        os.environ["ADMIN_UI_ROLE"] = "viewer"
        auth.ADMIN_UI_ROLE = "viewer"
        try:
            self.assertEqual(self._page().status_code, 403)
        finally:
            os.environ["ADMIN_UI_ROLE"] = "admin"
            auth.ADMIN_UI_ROLE = "admin"

    def test_regenerating_requires_a_matching_csrf_token_and_changes_nothing_without_it(self):
        mfa.store_backup_codes("admin", mfa.generate_backup_codes(count=2))
        before = self.redis.get(mfa._backup_codes_key("admin"))
        for headers in (self._totp(), {**self._totp(), "X-CSRF-Token": "abc"}):
            self.client.cookies.clear()
            response = self.client.post("/mfa/backup-codes", auth=self.auth, headers=headers)
            self.assertEqual(response.status_code, 403)
        self.client.cookies.set("csrf_token", "cookie-value")
        response = self.client.post(
            "/mfa/backup-codes", auth=self.auth, headers={**self._totp(), "X-CSRF-Token": "different"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.redis.get(mfa._backup_codes_key("admin")), before)

    def test_regeneration_returns_new_codes_once_uncached_and_logs_no_codes(self):
        token = secrets.token_urlsafe(16)
        self.client.cookies.set("csrf_token", token)
        with patch("src.admin_ui.auth.log_event") as logged:
            response = self.client.post(
                "/mfa/backup-codes", auth=self.auth, headers={**self._totp(), "X-CSRF-Token": token}
            )
        self.assertEqual(response.status_code, 200)
        codes = response.json()["backup_codes"]
        self.assertEqual(len(codes), mfa.BACKUP_CODE_COUNT)
        self.assertEqual(response.headers["cache-control"], "no-store")
        logged.assert_called_once()
        self.assertEqual(logged.call_args.args[1], "regenerate_backup_codes")
        self.assertEqual(logged.call_args.args[2], {"count": mfa.BACKUP_CODE_COUNT})
        for code in codes:
            self.assertNotIn(code, str(logged.call_args))
        # the status endpoint and page expose only counts
        status = mfa.get_backup_codes_status("admin")
        self.assertEqual((status["remaining"], status["total"]), (mfa.BACKUP_CODE_COUNT, mfa.BACKUP_CODE_COUNT))
        self.assertNotIn("codes", status)

    def test_script_confirms_sends_the_csrf_header_and_clears_the_codes(self):
        script = (STATIC / "security.js").read_text()
        self.assertIn("'X-CSRF-Token': csrfToken()", script)
        self.assertIn("confirmAction(\n        'Regenerate backup codes?'", script)
        self.assertIn("codesList.textContent = ''", script)
        self.assertIn("window.addEventListener('pagehide', hideCodes)", script)
        for storage in ("localStorage", "sessionStorage", "innerHTML", "console.log"):
            self.assertNotIn(storage, script)

    def test_backup_code_status_is_empty_when_redis_is_unavailable(self):
        with patch("src.admin_ui.mfa.get_redis_connection", return_value=None):
            self.assertEqual(mfa.get_backup_codes_status("admin"), {"remaining": 0, "total": 0, "created_at": None})
