"""Settings page: defaults, validity hints, last-changed and risky-change confirmation (#1953)."""

import dataclasses
import json
import os
import re
import secrets
import unittest
from unittest.mock import patch

import bcrypt
import pyotp
from fastapi.testclient import TestClient

from src.admin_ui import admin_ui, auth


class FakeRedis:
    def __init__(self):
        self.store = {}

    def hget(self, key, field):
        return self.store.get((key, field))

    def hset(self, key, field, value):
        self.store[(key, field)] = value
        return 1

    def hgetall(self, key):
        return {field: value for (name, field), value in self.store.items() if name == key}


def setting(redis: FakeRedis, name: str):
    return redis.store.get((admin_ui.RUNTIME_SETTINGS_KEY, name))


class SettingsUxTests(unittest.TestCase):
    def setUp(self):
        os.environ["ADMIN_UI_USERNAME"] = "admin"
        os.environ["ADMIN_UI_PASSWORD_HASH"] = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
        os.environ["ADMIN_UI_ROLE"] = "admin"
        os.environ["ADMIN_UI_2FA_SECRET"] = pyotp.random_base32()
        auth.ADMIN_UI_ROLE = "admin"
        self.redis = FakeRedis()
        for target, value in (
            ("src.admin_ui.admin_ui.get_redis_connection", self.redis),
            ("src.admin_ui.auth.get_redis_connection", None),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(admin_ui.app)
        self.auth = ("admin", "testpass")

    def _totp(self) -> dict:
        return {"X-2FA-Code": pyotp.TOTP(os.environ["ADMIN_UI_2FA_SECRET"]).now()}

    def _get(self):
        response = self.client.get("/settings", auth=self.auth, headers=self._totp())
        self.assertEqual(response.status_code, 200)
        return response

    def _post(self, **fields):
        token = self._get().cookies.get("csrf_token")
        self.client.cookies.set("csrf_token", token)
        return self.client.post(
            "/settings",
            auth=self.auth,
            headers=self._totp(),
            data={"csrf_token": token, **fields},
        )

    # ---- display -------------------------------------------------------------------------------------------

    def test_each_setting_shows_validity_startup_value_and_source(self):
        html = self._get().text
        self.assertIn("Valid: A whole number of at least 1.", html)
        self.assertIn("Valid: One of DEBUG, INFO, WARNING, ERROR, CRITICAL.", html)
        self.assertIn("Valid: An absolute http:// or https:// URL.", html)
        self.assertIn("Started as", html)
        self.assertRegex(html, r"\((environment variable|built-in default)\)")
        self.assertIn("No change recorded yet.", html)
        for key in admin_ui.EDITABLE_SETTING_MAP:
            self.assertIn(f'id="meta-{key}"', html)

    def test_risky_settings_are_flagged_on_the_page(self):
        html = self._get().text
        for key, setting_def in admin_ui.EDITABLE_SETTING_MAP.items():
            block = html.split(f'id="meta-{key}"', 1)[1].split("</p>", 1)[0]
            self.assertEqual("ask for confirmation" in block, setting_def.risky, key)
        self.assertEqual(
            sorted(k for k, v in admin_ui.EDITABLE_SETTING_MAP.items() if v.risky),
            ["ENABLE_HTTPS", "ESCALATION_ENDPOINT"],
        )

    def test_builtin_default_is_shown_when_the_environment_overrode_it(self):
        # pin both settings so the test does not depend on the environment the suite runs in
        pinned = {"RATE_LIMIT_REQUESTS": "250", "RATE_LIMIT_WINDOW": "60"}
        settings = tuple(
            dataclasses.replace(item, default=pinned[item.key]) if item.key in pinned else item
            for item in admin_ui.EDITABLE_SETTINGS
        )
        with patch.object(admin_ui, "EDITABLE_SETTINGS", settings), patch.dict(
            admin_ui.STARTUP_ENV, {"RATE_LIMIT_REQUESTS": "250", "RATE_LIMIT_WINDOW": None}
        ):
            html = self._get().text
        block = html.split('id="meta-RATE_LIMIT_REQUESTS"', 1)[1].split("</p>", 1)[0]
        self.assertIn("Started as <code>250</code> (environment variable)", block)
        self.assertIn("built-in default <code>100</code>", block)
        # a setting that started at its built-in default does not repeat it
        other = html.split('id="meta-RATE_LIMIT_WINDOW"', 1)[1].split("</p>", 1)[0]
        self.assertIn("(built-in default)", other)
        self.assertNotIn("; built-in default", other)

    # ---- last changed --------------------------------------------------------------------------------------

    def test_last_changed_comes_from_the_record_kept_beside_the_settings(self):
        meta = admin_ui.RUNTIME_SETTINGS_META_KEY
        self.redis.store[(meta, "LOG_LEVEL")] = json.dumps(
            {"actor": "bob", "at": "2026-03-03T11:00:00+00:00"}
        )
        self.redis.store[(meta, "NOT_A_SETTING")] = json.dumps({"actor": "x", "at": "y"})
        self.redis.store[(meta, "MAX_BODY_SIZE")] = "not json"
        html = self._get().text
        block = html.split('id="meta-LOG_LEVEL"', 1)[1].split("</p>", 1)[0]
        self.assertIn("Last changed by <strong>bob</strong> at 2026-03-03T11:00:00+00:00", block)
        other = html.split('id="meta-MAX_BODY_SIZE"', 1)[1].split("</p>", 1)[0]
        self.assertIn("No change recorded", other)

    def test_an_old_change_never_expires_however_much_has_been_audited_since(self):
        """The lookup does not read the bounded audit window at all."""
        self.redis.store[(admin_ui.RUNTIME_SETTINGS_META_KEY, "LOG_LEVEL")] = json.dumps(
            {"actor": "alice", "at": "2025-01-01T00:00:00+00:00"}
        )
        self.assertFalse(hasattr(admin_ui, "load_security_events"))
        html = self._get().text
        self.assertIn("Last changed by <strong>alice</strong> at 2025-01-01", html)

    def test_an_unreadable_change_record_does_not_break_the_page(self):
        with patch.object(FakeRedis, "hgetall", side_effect=RuntimeError("redis down")):
            self.assertEqual(self._get().status_code, 200)
            self.assertEqual(admin_ui._last_changes(), {})

    def test_saving_records_the_actor_only_for_settings_that_changed(self):
        self._get()  # seeds the runtime values
        before = admin_ui._last_changes()
        self.assertEqual(before, {})
        with patch("src.admin_ui.admin_ui.log_event") as logged:
            response = self._post(LOG_LEVEL="DEBUG")
        self.assertEqual(response.status_code, 200)
        details = logged.call_args.args[2]
        self.assertEqual(details["changed"], ["LOG_LEVEL"])
        recorded = admin_ui._last_changes()
        self.assertEqual(list(recorded), ["LOG_LEVEL"])
        self.assertEqual(recorded["LOG_LEVEL"]["actor"], "admin")
        self.assertRegex(recorded["LOG_LEVEL"]["at"], r"^20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d")
        # saving the same value again is a save but not a change: nothing is re-attributed
        self.redis.store[(admin_ui.RUNTIME_SETTINGS_META_KEY, "LOG_LEVEL")] = json.dumps(
            {"actor": "earlier-admin", "at": "2026-01-01T00:00:00+00:00"}
        )
        with patch("src.admin_ui.admin_ui.log_event") as logged:
            self._post(LOG_LEVEL="DEBUG")
        self.assertEqual(logged.call_args.args[2]["changed"], [])
        self.assertEqual(admin_ui._last_changes()["LOG_LEVEL"]["actor"], "earlier-admin")
        html = self._get().text
        self.assertIn("Last changed by <strong>earlier-admin</strong>", html)

    def test_a_change_made_on_the_plugins_page_is_attributed_too(self):
        self._get()
        self._seed("ALLOWED_PLUGINS", "ua_blocker")
        token = self._get().cookies.get("csrf_token")
        self.client.cookies.set("csrf_token", token)
        with patch("httpx.post"):
            response = self.client.post(
                "/plugins",
                auth=self.auth,
                headers=self._totp(),
                data={"csrf_token": token, "plugins": ["ua_blocker", "other_plugin"]},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(setting(self.redis, "ALLOWED_PLUGINS"), "ua_blocker,other_plugin")
        self.assertEqual(admin_ui._last_changes()["ALLOWED_PLUGINS"]["actor"], "admin")
        # the same selection again changes nothing, so the attribution is left alone
        self.redis.store[(admin_ui.RUNTIME_SETTINGS_META_KEY, "ALLOWED_PLUGINS")] = json.dumps(
            {"actor": "first", "at": "2026-01-01T00:00:00+00:00"}
        )
        with patch("httpx.post"):
            self.client.post(
                "/plugins",
                auth=self.auth,
                headers=self._totp(),
                data={"csrf_token": token, "plugins": ["ua_blocker", "other_plugin"]},
                follow_redirects=False,
            )
        self.assertEqual(admin_ui._last_changes()["ALLOWED_PLUGINS"]["actor"], "first")

    # ---- risky changes -------------------------------------------------------------------------------------

    def _seed(self, name: str, value: str):
        self.redis.store[(admin_ui.RUNTIME_SETTINGS_KEY, name)] = value

    def test_turning_the_https_redirect_off_needs_confirmation_and_saves_nothing_first(self):
        self._seed("ENABLE_HTTPS", "true")
        with patch("src.admin_ui.admin_ui.log_event") as logged:
            response = self._post(ENABLE_HTTPS="false")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Nothing has been saved yet", response.text)
        self.assertIn("Plain HTTP requests will no longer be redirected to HTTPS.", response.text)
        self.assertEqual(setting(self.redis, "ENABLE_HTTPS"), "true")
        logged.assert_not_called()
        token = re.search(r'name="confirm_risky" value="([0-9a-f]{64})"', response.text).group(1)

        with patch("src.admin_ui.admin_ui.log_event") as logged:
            response = self._post(ENABLE_HTTPS="false", confirm_risky=token)
        self.assertNotIn("Nothing has been saved yet", response.text)
        self.assertEqual(setting(self.redis, "ENABLE_HTTPS"), "false")
        self.assertIn("ENABLE_HTTPS", logged.call_args.args[2]["changed"])

    def test_changing_the_escalation_url_needs_confirmation(self):
        self._get()
        old = setting(self.redis, "ESCALATION_ENDPOINT")
        response = self._post(ESCALATION_ENDPOINT="https://example.org/escalate")
        self.assertIn("Nothing has been saved yet", response.text)
        self.assertIn("https://example.org/escalate", response.text)
        self.assertEqual(setting(self.redis, "ESCALATION_ENDPOINT"), old)

    def test_a_confirmation_cannot_be_reused_for_different_values(self):
        self._get()
        first = self._post(ESCALATION_ENDPOINT="https://example.org/a")
        token = re.search(r'name="confirm_risky" value="([0-9a-f]{64})"', first.text).group(1)
        old = setting(self.redis, "ESCALATION_ENDPOINT")
        second = self._post(ESCALATION_ENDPOINT="https://evil.example/b", confirm_risky=token)
        self.assertIn("Nothing has been saved yet", second.text)
        self.assertEqual(setting(self.redis, "ESCALATION_ENDPOINT"), old)
        for bad in ("", "x" * 64, "0" * 64):
            response = self._post(ESCALATION_ENDPOINT="https://example.org/a", confirm_risky=bad)
            self.assertIn("Nothing has been saved yet", response.text)
        self.assertEqual(setting(self.redis, "ESCALATION_ENDPOINT"), old)

    def test_safe_changes_save_without_a_confirmation_step(self):
        self._seed("ENABLE_HTTPS", "false")
        self._get()
        response = self._post(ENABLE_HTTPS="true", LOG_LEVEL="WARNING")  # turning the redirect ON is not a weakening
        self.assertNotIn("Nothing has been saved yet", response.text)
        self.assertEqual(setting(self.redis, "ENABLE_HTTPS"), "true")
        self.assertEqual(setting(self.redis, "LOG_LEVEL"), "WARNING")
        # an unchanged risky value does not ask either
        response = self._post(ENABLE_HTTPS="true")
        self.assertNotIn("Nothing has been saved yet", response.text)

    def test_validation_errors_still_appear_next_to_the_field_and_save_nothing(self):
        self._get()
        before = dict(self.redis.store)
        response = self._post(RATE_LIMIT_REQUESTS="0", ESCALATION_ENDPOINT="not-a-url")
        self.assertEqual(response.status_code, 400)
        self.assertIn("must be a positive integer", response.text)
        self.assertIn("must be an absolute http(s) URL", response.text)
        self.assertEqual(self.redis.store, before)

    def test_the_csrf_check_still_applies(self):
        self._get()
        response = self.client.post(
            "/settings",
            auth=self.auth,
            headers=self._totp(),
            data={"csrf_token": secrets.token_urlsafe(8), "LOG_LEVEL": "DEBUG"},
        )
        self.assertEqual(response.status_code, 400)
