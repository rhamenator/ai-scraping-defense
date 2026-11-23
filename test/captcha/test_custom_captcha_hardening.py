"""One-time, client-bound CAPTCHA challenges and their limits (#1903)."""

import base64
import re
import secrets
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.captcha import custom_captcha_service as svc
from src.captcha.challenge_store import ChallengeStore


def parse(page: str) -> tuple[str, str]:
    token = page.split("name='token' value='", 1)[1].split("'", 1)[0]
    a, b = re.search(r"What is (\d+) \+ (\d+)", page).groups()
    return token, str(int(a) + int(b))


class Base(unittest.TestCase):
    def setUp(self):
        secret = secrets.token_urlsafe(12)
        patcher = patch.multiple(svc, CAPTCHA_SECRET=secret, store=ChallengeStore("memory"), RATE_LIMIT_PER_MINUTE=1000, BIND_IP=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.secret = secret
        self.client = TestClient(svc.app)

    def issue(self, client=None, **kwargs):
        page = (client or self.client).get("/challenge", **kwargs).text
        return parse(page)

    def solve(self, token, answer, client=None, **kwargs):
        return (client or self.client).post("/solve", data={"answer": answer, "token": token}, **kwargs).json()


class ChallengeSecrecy(Base):
    def test_the_token_is_an_opaque_random_id_with_nothing_encoded_in_it(self):
        token, _answer = self.issue()
        self.assertRegex(token, r"^[A-Za-z0-9_-]{32}$", "a 24-byte random id, URL-safe, nothing else")
        decoded = base64.urlsafe_b64decode(token)
        self.assertEqual(len(decoded), 24)
        self.assertNotIn(b'"ans"', decoded, "not a JSON payload carrying the answer")

    def test_the_page_does_not_carry_the_answer_or_a_signed_payload_anywhere(self):
        page = self.client.get("/challenge").text
        token, answer = parse(page)
        self.assertNotIn("ans", token)
        self.assertIsNone(re.search(r"name='token' value='[^']*\.", page), "no payload.signature form")

    def test_tokens_are_random_and_never_repeat(self):
        self.assertEqual(len({self.issue()[0] for _ in range(20)}), 20)


class PageBehaviour(Base):
    def test_a_missed_answer_loads_a_fresh_question_and_the_result_is_announced(self):
        page = self.client.get("/challenge").text
        self.assertIn("location.reload()", page, "a consumed challenge cannot be resubmitted, so the page asks for a new one")
        self.assertIn("aria-live='polite'", page, "screen readers hear the result")
        self.assertNotIn("Try again", page)


class OneTimeUse(Base):
    def test_a_challenge_can_be_answered_only_once(self):
        token, answer = self.issue()
        self.assertTrue(self.solve(token, answer)["success"])
        self.assertFalse(self.solve(token, answer)["success"], "replaying the same solved challenge fails")

    def test_a_wrong_answer_also_consumes_the_challenge(self):
        token, answer = self.issue()
        self.assertFalse(self.solve(token, "999")["success"])
        self.assertFalse(self.solve(token, answer)["success"], "one attempt per challenge: no guessing the small answer space")

    def test_an_unknown_or_forged_token_fails(self):
        self.assertFalse(self.solve("not-a-real-id", "5")["success"])
        self.assertFalse(self.solve(svc._sign({"ans": 5, "exp": 9999999999}), "5")["success"])

    def test_an_expired_challenge_fails(self):
        with patch("src.captcha.challenge_store.time.monotonic", return_value=0.0):
            token, answer = self.issue()
        with patch("src.captcha.challenge_store.time.monotonic", return_value=10**6):
            self.assertFalse(self.solve(token, answer)["success"])


class ClientBinding(Base):
    def test_a_different_client_address_cannot_solve_it(self):
        token, answer = self.issue(headers={"x-forwarded-for": "198.51.100.1"})
        with patch.object(svc, "resolve_request_identity") as ident:
            ident.return_value.client_ip = "203.0.113.50"
            self.assertFalse(self.solve(token, answer)["success"])

    def test_the_same_address_can(self):
        with patch.object(svc, "resolve_request_identity") as ident:
            ident.return_value.client_ip = "203.0.113.50"
            token, answer = self.issue()
            self.assertTrue(self.solve(token, answer)["success"])

    def test_address_binding_can_be_turned_off(self):
        with patch.object(svc, "resolve_request_identity") as ident, patch.object(svc, "BIND_IP", False):
            ident.return_value.client_ip = "203.0.113.50"
            token, answer = self.issue()
            ident.return_value.client_ip = "198.51.100.9"
            self.assertTrue(self.solve(token, answer)["success"])

    def test_a_different_browser_fingerprint_cannot_solve_it(self):
        self.client.cookies.set("fp_id", "fp-a")
        token, answer = self.issue()
        self.client.cookies.set("fp_id", "fp-b")
        self.assertFalse(self.solve(token, answer)["success"])

    def test_the_same_browser_fingerprint_can(self):
        self.client.cookies.set("fp_id", "fp-a")
        token, answer = self.issue()
        self.assertTrue(self.solve(token, answer)["success"])


class RateLimit(Base):
    def test_challenges_are_limited_per_client_per_minute(self):
        with patch.object(svc, "RATE_LIMIT_PER_MINUTE", 3):
            codes = [self.client.get("/challenge").status_code for _ in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])

    def test_solve_attempts_are_limited_too(self):
        with patch.object(svc, "RATE_LIMIT_PER_MINUTE", 2):
            codes = [self.client.post("/solve", data={"answer": "1", "token": secrets.token_hex(4)}).status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 429, 429])

    def test_zero_disables_the_limit(self):
        with patch.object(svc, "RATE_LIMIT_PER_MINUTE", 0):
            self.assertTrue(all(self.client.get("/challenge").status_code == 200 for _ in range(10)))


class VerifyCompatibility(Base):
    def final_token(self):
        token, answer = self.issue()
        return self.solve(token, answer)["token"]

    def test_query_parameters_still_work(self):
        final = self.final_token()
        self.assertTrue(self.client.post("/verify", params={"token": final, "ip": "testclient"}).json()["success"])
        self.assertFalse(self.client.post("/verify", params={"token": final, "ip": "203.0.113.9"}).json()["success"])

    def test_the_form_the_escalation_engine_sends_works(self):
        final = self.final_token()
        ok = self.client.post("/verify", data={"secret": self.secret, "response": final, "remoteip": "testclient"})
        self.assertTrue(ok.json()["success"])

    def test_a_wrong_secret_or_ip_is_refused(self):
        final = self.final_token()
        bad_secret = self.client.post("/verify", data={"secret": secrets.token_hex(8), "response": final, "remoteip": "testclient"})
        self.assertFalse(bad_secret.json()["success"])
        bad_ip = self.client.post("/verify", data={"secret": self.secret, "response": final, "remoteip": "203.0.113.9"})
        self.assertFalse(bad_ip.json()["success"])

    def test_missing_input_is_a_clean_failure_not_an_error(self):
        self.assertFalse(self.client.post("/verify").json()["success"])
        self.assertFalse(self.client.post("/verify", params={"token": secrets.token_hex(4)}).json()["success"])

    def test_each_issued_token_is_distinct(self):
        self.assertNotEqual(self.final_token(), self.final_token())


class SuccessLog(Base):
    def test_the_log_marks_its_source_as_untrusted_telemetry(self):
        import json
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "captcha.log")
            with patch.object(svc, "CAPTCHA_SUCCESS_LOG", path):
                token, answer = self.issue()
                self.solve(token, answer)
            entry = json.loads(open(path).read().splitlines()[0])
        self.assertEqual(entry["source"], "captcha_service")


class StoreBehaviour(unittest.TestCase):
    def test_take_is_atomic_across_threads(self):
        import threading

        store = ChallengeStore("memory")
        store.put("c1", {"ans": 3}, 60)
        winners = []
        threads = [threading.Thread(target=lambda: winners.append(store.take("c1"))) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum(1 for w in winners if w), 1)

    def test_the_rate_window_resets(self):
        store = ChallengeStore("memory")
        with patch("src.captcha.challenge_store.time.monotonic", return_value=0.0):
            self.assertEqual([store.allow("k", 2) for _ in range(3)], [True, True, False])
        with patch("src.captcha.challenge_store.time.monotonic", return_value=120.0):
            self.assertTrue(store.allow("k", 2))


if __name__ == "__main__":
    unittest.main()
