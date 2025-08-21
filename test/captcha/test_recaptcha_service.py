import asyncio
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.requests import Request


class TestRecaptchaService(unittest.TestCase):
    def setUp(self):
        os.environ["CAPTCHA_SECRET"] = "testsecret"
        from src.captcha import recaptcha_service as svc

        self.svc = svc
        self.svc.CAPTCHA_SECRET = "testsecret"
        self.tmpdir = tempfile.mkdtemp()
        self.svc.CAPTCHA_SUCCESS_LOG = os.path.join(self.tmpdir, "captcha.log")
        self.client = TestClient(self.svc.app)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_verify_uses_client_ip(self):
        captured = {}

        async def mock_post(self, url, data=None, timeout=10.0):
            captured["data"] = data

            class MockResp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"success": True}

            return MockResp()

        with patch("httpx.AsyncClient.post", new=mock_post):
            resp = self.client.post("/verify", params={"token": "abc"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(captured["data"]["remoteip"], "testclient")

    def test_verify_without_client_ip_omits_remoteip(self):
        captured = {}

        async def mock_post(self, url, data=None, timeout=10.0):
            captured["data"] = data

            class MockResp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"success": True}

            return MockResp()

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "method": "POST",
            "path": "/verify",
            "raw_path": b"/verify",
            "query_string": b"",
            "root_path": "",
            "scheme": "http",
            "client": None,
            "server": ("testserver", 80),
            "headers": [],
        }
        req = Request(scope)
        with patch("httpx.AsyncClient.post", new=mock_post):
            result = asyncio.run(self.svc.verify_captcha("abc", req))
        self.assertTrue(result["success"])
        self.assertNotIn("remoteip", captured["data"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
