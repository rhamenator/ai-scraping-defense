"""Tests for CAPTCHA provider selection, accessible question types, and manual access requests."""

import re
import secrets
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.admin_ui import admin_ui
from src.captcha import custom_captcha_service as svc
from src.captcha.access_requests import AccessRequestStore
from src.captcha.challenge_store import ChallengeStore
from src.captcha.questions import _COLOR_WORDS
from src.shared.config import resolve_captcha_verification_url


class ProviderSelectionTests(unittest.TestCase):
    def test_resolve_verification_urls(self):
        self.assertEqual(
            resolve_captcha_verification_url("builtin", None),
            "http://captcha_service:8004/verify",
        )
        self.assertEqual(
            resolve_captcha_verification_url("recaptcha", None),
            "https://www.google.com/recaptcha/api/siteverify",
        )
        self.assertEqual(
            resolve_captcha_verification_url("turnstile", None),
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        )
        self.assertEqual(
            resolve_captcha_verification_url("turnstile", "https://custom.example/verify"),
            "https://custom.example/verify",
        )

    def test_builtin_endpoints_disabled_when_external_provider_configured(self):
        dummy_secret = secrets.token_urlsafe(12)
        dummy_token = secrets.token_urlsafe(8)
        with patch.multiple(svc, CAPTCHA_PROVIDER="turnstile", CAPTCHA_SECRET=dummy_secret):
            client = TestClient(svc.app)
            self.assertEqual(client.get("/challenge").status_code, 404)
            self.assertEqual(client.post("/solve", data={"answer": "1", "token": dummy_token}).status_code, 404)
            self.assertEqual(client.post("/verify", params={"token": dummy_token, "ip": "1.2.3.4"}).status_code, 404)
            self.assertEqual(client.post("/request-access", data={"note": "help"}).status_code, 404)

    def test_runtime_setting_propagation_disables_builtin_and_toggles_requests(self):
        with patch("src.captcha.custom_captcha_service.get_runtime_setting") as mock_setting:
            mock_setting.side_effect = lambda k, d: "turnstile" if k == "CAPTCHA_PROVIDER" else d
            client = TestClient(svc.app)
            self.assertEqual(client.get("/challenge").status_code, 404)

        with patch("src.captcha.custom_captcha_service.get_runtime_setting") as mock_setting:
            mock_setting.side_effect = lambda k, d: "true" if k == "CAPTCHA_MANUAL_REQUESTS_ENABLED" else d
            req_store = AccessRequestStore("memory")
            with patch.object(svc, "request_store", req_store):
                client = TestClient(svc.app)
                res = client.post("/request-access", data={"note": "propagated"})
                self.assertEqual(res.status_code, 200)


class AccessibleQuestionTypesTests(unittest.TestCase):
    def setUp(self):
        self.patcher = patch.multiple(
            svc,
            CAPTCHA_PROVIDER="builtin",
            CAPTCHA_SECRET=secrets.token_urlsafe(12),
            store=ChallengeStore("memory"),
            RATE_LIMIT_PER_MINUTE=1000,
            BIND_IP=True,
            MIN_SOLVE_SECONDS=0,
            REQUIRE_PROOF=True,
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = TestClient(svc.app)

    def test_color_and_word_questions_render_read_aloud_and_solve(self):
        color_page = self.client.get("/challenge?type=color").text
        self.assertIn("Read question aloud", color_page)
        self.assertIn("speechSynthesis", color_page)
        token = color_page.split("name='token' value='", 1)[1].split("'", 1)[0]
        words = re.search(r"Which of these words is a colour\? ([^<]+)", color_page).group(1).split(", ")
        color_answer = next(w.strip() for w in words if w.strip() in _COLOR_WORDS)
        res = self.client.post(
            "/solve",
            data={"answer": color_answer.upper(), "token": token, "proof": svc._proof(token, color_answer.upper())},
        ).json()
        self.assertTrue(res["success"])

        word_page = self.client.get("/challenge?type=word").text
        token_w = word_page.split("name='token' value='", 1)[1].split("'", 1)[0]
        word_answer = re.search(r"Type this word to continue: (\w+)", word_page).group(1)
        res_w = self.client.post(
            "/solve",
            data={"answer": word_answer, "token": token_w, "proof": svc._proof(token_w, word_answer)},
        ).json()
        self.assertTrue(res_w["success"])

    def test_accessible_types_still_enforce_min_solve_time(self):
        with patch.object(svc, "MIN_SOLVE_SECONDS", 2.0):
            word_page = self.client.get("/challenge?type=word").text
            token_w = word_page.split("name='token' value='", 1)[1].split("'", 1)[0]
            word_answer = re.search(r"Type this word to continue: (\w+)", word_page).group(1)
            res = self.client.post(
                "/solve",
                data={"answer": word_answer, "token": token_w, "proof": svc._proof(token_w, word_answer)},
            ).json()
            self.assertEqual(res, {"success": False, "retry": True})


class ManualAccessRequestTests(unittest.TestCase):
    def test_manual_request_endpoint_is_off_by_default(self):
        with patch.multiple(svc, CAPTCHA_PROVIDER="builtin", MANUAL_REQUESTS_ENABLED=False):
            client = TestClient(svc.app)
            self.assertEqual(client.post("/request-access", data={"note": "hi"}).status_code, 404)

    def test_submit_cooldown_cap_approve_and_xss_escape(self):
        req_store = AccessRequestStore("memory")
        with (
            patch.multiple(
                svc,
                CAPTCHA_PROVIDER="builtin",
                CAPTCHA_SECRET=secrets.token_urlsafe(12),
                store=ChallengeStore("memory"),
                request_store=req_store,
                MANUAL_REQUESTS_ENABLED=True,
                RATE_LIMIT_PER_MINUTE=1000,
            ),
            patch.dict("os.environ", {"CAPTCHA_REQUEST_MAX_PENDING": "2", "CAPTCHA_REQUEST_COOLDOWN_SECONDS": "3600"}),
        ):
            client = TestClient(svc.app)
            page = client.get("/challenge").text
            self.assertIn("Ask admin to let me in", page)

            first = client.post("/request-access", data={"note": "<script>alert(1)</script>"})
            self.assertEqual(first.status_code, 200)
            req_id = first.json()["id"]

            dup = client.post("/request-access", data={"note": "again"})
            self.assertEqual(dup.status_code, 429)
            self.assertEqual(dup.json()["status"], "already_pending")

            # Approve grants temporary IP allowlist and clears pending.
            approved = req_store.approve(req_id, actor="admin")
            self.assertEqual(approved["status"], "approved")
            self.assertTrue(req_store.is_temporarily_allowed("testclient"))

            # Cooldown still blocks immediate re-submission from the same IP.
            cd = client.post("/request-access", data={"note": "after approve"})
            self.assertEqual(cd.status_code, 429)
            self.assertEqual(cd.json()["status"], "cooldown")

    def test_global_queue_cap_pauses_requests(self):
        req_store = AccessRequestStore("memory")
        with patch.dict("os.environ", {"CAPTCHA_REQUEST_MAX_PENDING": "1", "CAPTCHA_REQUEST_COOLDOWN_SECONDS": "0"}):
            ok, status, _ = req_store.submit("198.51.100.1", "first")
            self.assertTrue(ok)
            self.assertEqual(status, "queued")
            ok2, status2, _ = req_store.submit("198.51.100.2", "second")
            self.assertFalse(ok2)
            self.assertEqual(status2, "paused")

    def test_admin_ui_escapes_notes_and_gates_cloudflare_banner(self):
        req_store = AccessRequestStore("memory")
        req_store.submit("198.51.100.5", "<img src=x onerror=alert(1)>")
        admin_ui.app.dependency_overrides[admin_ui.require_auth] = lambda: "admin"
        self.addCleanup(admin_ui.app.dependency_overrides.clear)

        with (
            patch.object(admin_ui, "access_request_store", req_store),
            patch.object(admin_ui, "_current_blocked_volume", return_value=200),
            patch.object(
                admin_ui,
                "_safe_runtime_setting",
                side_effect=lambda k, d: {"CLOUDFLARE_ENABLED": "false", "CLOUDFLARE_UNDER_ATTACK_THRESHOLD": "100"}.get(k, d),
            ),
        ):
            client = TestClient(admin_ui.app)
            html = client.get("/").text
            self.assertNotIn("<img src=x", html)
            self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
            self.assertNotIn("cloudflare-under-attack-banner", html)

        with (
            patch.object(admin_ui, "access_request_store", req_store),
            patch.object(admin_ui, "_current_blocked_volume", return_value=200),
            patch.object(
                admin_ui,
                "_safe_runtime_setting",
                side_effect=lambda k, d: {"CLOUDFLARE_ENABLED": "true", "CLOUDFLARE_UNDER_ATTACK_THRESHOLD": "100"}.get(k, d),
            ),
        ):
            client = TestClient(admin_ui.app)
            html = client.get("/").text
            self.assertIn("cloudflare-under-attack-banner", html)

    def test_approve_unblocks_ip_via_blocklist_store(self):
        req_store = AccessRequestStore("memory")
        _, _, rec = req_store.submit("198.51.100.77", "blocked by mistake")
        admin_ui.app.dependency_overrides[admin_ui.require_admin] = lambda: "admin"
        self.addCleanup(admin_ui.app.dependency_overrides.clear)
        csrf = secrets.token_urlsafe(12)
        with (
            patch.object(admin_ui, "access_request_store", req_store),
            patch("src.admin_ui.admin_ui.blocklist_store.unblock", return_value=True) as mock_unblock,
        ):
            client = TestClient(admin_ui.app)
            client.cookies.set("csrf_token", csrf)
            res = client.post(
                f"/captcha-requests/{rec['id']}/approve",
                data={"csrf_token": csrf},
            )
            self.assertEqual(res.status_code, 200)
            mock_unblock.assert_called_once_with("198.51.100.77")
            self.assertTrue(req_store.is_temporarily_allowed("198.51.100.77"))


if __name__ == "__main__":
    unittest.main()
