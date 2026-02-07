import importlib
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestPayPerCrawlProxy(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"UPSTREAM_URL": "http://example.com"})
        self.env.start()
        import src.pay_per_crawl.proxy as proxy

        importlib.reload(proxy)
        self.proxy = proxy
        self.client = TestClient(self.proxy.app)

        self.patches = {
            "get_crawler": patch(
                "src.pay_per_crawl.proxy.get_crawler", return_value={"token": "tok"}
            ),
            "charge": patch("src.pay_per_crawl.proxy.charge", return_value=True),
            "AsyncClient": patch("src.pay_per_crawl.proxy.httpx.AsyncClient"),
        }
        self.mocks = {name: p.start() for name, p in self.patches.items()}
        async_client_instance = AsyncMock()
        async_client_instance.request.return_value = MagicMock(
            content=b"ok", status_code=200, headers={}
        )
        self.mocks["AsyncClient"].return_value.__aenter__.return_value = (
            async_client_instance
        )

    def tearDown(self):
        for p in self.patches.values():
            p.stop()
        self.env.stop()

    def test_invalid_path_rejected(self):
        resp = self.client.get("/..%2Fetc/passwd", headers={"X-API-Key": "tok"})
        self.assertEqual(resp.status_code, 400)

    def test_path_length_rejected(self):
        resp = self.client.get("/" + "a" * 3000, headers={"X-API-Key": "tok"})
        self.assertEqual(resp.status_code, 414)

    def test_valid_path_proxies(self):
        resp = self.client.get("/api/data", headers={"X-API-Key": "tok"})
        self.assertEqual(resp.status_code, 200)
        called_url = self.mocks[
            "AsyncClient"
        ].return_value.__aenter__.return_value.request.call_args[0][1]
        self.assertEqual(called_url, "http://example.com/api/data")

    def test_urlparse_import_available(self):
        """Verify urlparse is properly imported and accessible"""
        # This test ensures that urlparse from urllib.parse is available
        # Addresses issue: urlparse import should be verified to ensure it's available
        from urllib.parse import urlparse

        self.assertTrue(callable(urlparse))
        # Verify it's the same one used in the proxy module
        self.assertIs(urlparse, self.proxy.urlparse)

    def test_ssrf_protection_scheme_mismatch(self):
        """Test SSRF protection rejects requests with mismatched scheme"""
        # Defense-in-depth: Even if initial validation is bypassed,
        # the SSRF check should catch scheme mismatches
        with patch(
            "src.pay_per_crawl.proxy.urljoin", return_value="https://evil.com/data"
        ):
            resp = self.client.get("/data", headers={"X-API-Key": "tok"})
            self.assertEqual(resp.status_code, 400)
            self.assertIn("Invalid upstream URL", resp.json()["detail"])

    def test_ssrf_protection_netloc_mismatch(self):
        """Test SSRF protection rejects requests with mismatched netloc"""
        # Defense-in-depth: Even if initial validation is bypassed,
        # the SSRF check should catch host mismatches
        with patch(
            "src.pay_per_crawl.proxy.urljoin", return_value="http://evil.com/data"
        ):
            resp = self.client.get("/data", headers={"X-API-Key": "tok"})
            self.assertEqual(resp.status_code, 400)
            self.assertIn("Invalid upstream URL", resp.json()["detail"])

    def test_absolute_url_with_scheme_rejected(self):
        """Test that absolute URLs with scheme are rejected by initial validation"""
        # Realistic attack: Try to use absolute URL
        resp = self.client.get(
            "/http://evil.com/malicious", headers={"X-API-Key": "tok"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid path", resp.json()["detail"])

    def test_protocol_relative_url_rejected(self):
        """Test that protocol-relative URLs are rejected"""
        # Realistic attack: Try protocol-relative URL (//host/path)
        # Note: FastAPI decodes the path, so we encode the slashes
        resp = self.client.get("/%2F%2Fevil.com/data", headers={"X-API-Key": "tok"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid path", resp.json()["detail"])

    def test_ssrf_protection_allows_valid_upstream(self):
        """Test that valid upstream URLs are allowed through"""
        # Normal case: urljoin produces a URL with same scheme and netloc
        resp = self.client.get("/api/data", headers={"X-API-Key": "tok"})
        self.assertEqual(resp.status_code, 200)

    def test_pay_rejects_negative_amount(self):
        resp = self.client.post("/pay", json={"token": "tok", "amount": -1})
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
