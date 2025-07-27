import json
import os
import unittest

from fastapi.testclient import TestClient

from src.captcha import custom_captcha_service as svc


class TestCustomCaptcha(unittest.TestCase):
    def setUp(self):
        os.environ["CAPTCHA_SECRET"] = "testsecret"
        self.client = TestClient(svc.app)

    def test_full_flow(self):
        resp = self.client.get("/challenge")
        self.assertEqual(resp.status_code, 200)
        # Extract token from hidden field
        token_marker = "name='token' value='"
        start = resp.text.find(token_marker) + len(token_marker)
        token = resp.text[start:].split("'")[0]
        solve = self.client.post(
            "/solve",
            data={"answer": "2", "token": token},
            headers={"User-Agent": "pytest"},
        )
        data = solve.json()
        self.assertTrue(data["success"])
        verify = self.client.post(
            "/verify", data={"token": data["token"], "ip": "test"}
        )
        self.assertTrue(verify.json()["success"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
