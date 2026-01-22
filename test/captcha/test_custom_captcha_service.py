import json
import os
import secrets
import unittest

from fastapi.testclient import TestClient

from src.captcha import custom_captcha_service as svc


class TestCustomCaptcha(unittest.TestCase):
    def setUp(self):
        secret = secrets.token_urlsafe(12)
        os.environ["CAPTCHA_SECRET"] = secret
        svc.CAPTCHA_SECRET = secret
        self.client = TestClient(svc.app)

    def test_full_flow(self):
        resp = self.client.get("/challenge")
        self.assertEqual(resp.status_code, 200)
        token_marker = "name='token' value='"
        start = resp.text.find(token_marker) + len(token_marker)
        token = resp.text[start:].split("'")[0]
        # parse numbers from challenge
        import re

        m = re.search(r"What is (\d+) \+ (\d+)", resp.text)
        answer = str(int(m.group(1)) + int(m.group(2))) if m else "0"
        solve = self.client.post(
            "/solve",
            data={"answer": answer, "token": token},
            headers={"User-Agent": "pytest"},
        )
        data = solve.json()
        self.assertTrue(data["success"])
        verify = self.client.post(
            "/verify", params={"token": data["token"], "ip": "testclient"}
        )
        self.assertTrue(verify.json()["success"])

    def test_invalid_answer(self):
        resp = self.client.get("/challenge")
        self.assertEqual(resp.status_code, 200)
        token_marker = "name='token' value='"
        start = resp.text.find(token_marker) + len(token_marker)
        token = resp.text[start:].split("'")[0]
        solve = self.client.post(
            "/solve",
            data={"answer": "abc", "token": token},
            headers={"User-Agent": "pytest"},
        )
        data = solve.json()
        self.assertFalse(data["success"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
