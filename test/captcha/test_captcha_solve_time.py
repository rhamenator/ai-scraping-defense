"""Too-fast solves and missing client proofs ask again; they never block or label anyone (#1903 follow-up)."""

import re
import secrets
import shutil
import subprocess  # nosec B404 - runs node on a fixed snippet to compare the page's proof function
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
        patcher = patch.multiple(
            svc, CAPTCHA_SECRET=secrets.token_urlsafe(12), store=ChallengeStore("memory"), RATE_LIMIT_PER_MINUTE=1000,
            BIND_IP=True, MIN_SOLVE_SECONDS=1.5, REQUIRE_PROOF=True,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(svc.app)

    def issue(self):
        return parse(self.client.get("/challenge").text)

    def solve(self, token, answer, proof="auto"):
        data = {"answer": answer, "token": token}
        if proof == "auto":
            proof = svc._proof(token, answer)
        if proof is not None:
            data["proof"] = proof
        return self.client.post("/solve", data=data)


class SolveTime(Base):
    def test_a_correct_answer_that_is_too_fast_asks_again_instead_of_failing_or_blocking(self):
        token, answer = self.issue()

        response = self.solve(token, answer)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": False, "retry": True})

    def test_the_challenge_is_consumed_so_the_visitor_needs_a_fresh_one(self):
        token, answer = self.issue()
        self.solve(token, answer)

        self.assertEqual(self.solve(token, answer).json(), {"success": False}, "no retry hint for a used challenge")

    def test_a_correct_answer_after_the_minimum_time_with_the_proof_passes(self):
        with patch("src.captcha.custom_captcha_service.time.time", return_value=1_000.0):
            token, answer = self.issue()
        with patch("src.captcha.custom_captcha_service.time.time", return_value=1_002.0):
            result = self.solve(token, answer).json()

        self.assertTrue(result["success"])
        self.assertIn("token", result)

    def test_the_boundary_is_the_configured_minimum(self):
        for elapsed, passes in ((1.4, False), (1.5, True), (60.0, True)):
            with self.subTest(elapsed=elapsed):
                with patch("src.captcha.custom_captcha_service.time.time", return_value=1_000.0):
                    token, answer = self.issue()
                with patch("src.captcha.custom_captcha_service.time.time", return_value=1_000.0 + elapsed):
                    self.assertEqual(self.solve(token, answer).json().get("success", False), passes)

    def test_a_wrong_answer_is_an_ordinary_failure_not_a_retry(self):
        token, _ = self.issue()
        with patch("src.captcha.custom_captcha_service.time.time", return_value=10_000_000.0):
            self.assertEqual(self.solve(token, "999").json(), {"success": False})

    def test_zero_disables_the_minimum(self):
        with patch.object(svc, "MIN_SOLVE_SECONDS", 0):
            token, answer = self.issue()
            self.assertTrue(self.solve(token, answer).json()["success"])


class ClientProof(Base):
    def passes_time(self):
        return patch.object(svc, "MIN_SOLVE_SECONDS", 0)

    def test_a_missing_or_wrong_proof_asks_again(self):
        with self.passes_time():
            for proof in (None, "", "00000000", "zzzzzzzz"):
                with self.subTest(proof=proof):
                    token, answer = self.issue()
                    self.assertEqual(self.solve(token, answer, proof=proof).json(), {"success": False, "retry": True})

    def test_a_proof_for_a_different_challenge_or_answer_does_not_work(self):
        with self.passes_time():
            token, answer = self.issue()
            other, other_answer = self.issue()
            self.assertTrue(self.solve(other, other_answer, proof=svc._proof(token, answer)).json().get("retry"))
            token, answer = self.issue()
            self.assertTrue(self.solve(token, answer, proof=svc._proof(token, "0")).json().get("retry"))

    def test_the_proof_is_case_and_whitespace_tolerant_and_covers_a_padded_answer(self):
        with self.passes_time():
            token, answer = self.issue()
            self.assertTrue(self.solve(token, f" {answer} ", proof=svc._proof(token, answer).upper()).json()["success"])

    def test_it_can_be_turned_off(self):
        with self.passes_time(), patch.object(svc, "REQUIRE_PROOF", False):
            token, answer = self.issue()
            self.assertTrue(self.solve(token, answer, proof=None).json()["success"])

    def test_the_javascript_proof_matches_the_python_one(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        page = self.client.get("/challenge").text
        function = re.search(r"function proof\(text\) \{.*?\n\}", page, re.S).group(0)
        samples = [("abc", "5"), ("A_b-9" * 6, "16"), ("t0k3n", "2"), ("", ""), ("x" * 32, "11")]
        script = function + "\n" + "\n".join(f"console.log(proof({t!r} + ':' + {a!r}));" for t, a in samples)
        out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, check=True).stdout.split()  # nosec B603
        self.assertEqual(out, [svc._proof(t, a) for t, a in samples])


class NothingIsBlockedOrLabelled(Base):
    def test_a_too_fast_solve_writes_no_success_log_and_issues_no_token(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            log = os.path.join(directory, "captcha.log")
            with patch.object(svc, "CAPTCHA_SUCCESS_LOG", log):
                token, answer = self.issue()
                result = self.solve(token, answer).json()
            self.assertNotIn("token", result)
            self.assertFalse(os.path.exists(log))

    def test_the_page_sends_the_proof_and_handles_the_retry_hint(self):
        page = self.client.get("/challenge").text
        self.assertIn("data.set('proof'", page)
        self.assertIn("js.retry", page)
        self.assertIn("Please take a moment", page)
        self.assertNotIn("<input type='hidden' name='proof'", page, "no extra field or control is added for anyone to see")


if __name__ == "__main__":
    unittest.main()
