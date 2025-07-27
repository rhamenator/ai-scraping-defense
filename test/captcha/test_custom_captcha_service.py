import json
import os
import unittest

from fastapi.testclient import TestClient

from src.captcha import custom_captcha_service as svc


class TestCustomCaptcha(unittest.TestCase):
    def setUp(self):
        os.environ["CAPTCHA_SECRET"] = "testsecret"
        svc.CAPTCHA_SECRET = "testsecret"
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
