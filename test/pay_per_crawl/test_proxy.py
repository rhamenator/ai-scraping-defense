import os
import importlib
import unittest
from unittest.mock import patch, AsyncMock, MagicMock
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
            "get_crawler": patch("src.pay_per_crawl.proxy.get_crawler", return_value={"token": "tok"}),
            "charge": patch("src.pay_per_crawl.proxy.charge", return_value=True),
            "AsyncClient": patch("src.pay_per_crawl.proxy.httpx.AsyncClient"),
        }
        self.mocks = {name: p.start() for name, p in self.patches.items()}
        async_client_instance = AsyncMock()
        async_client_instance.request.return_value = MagicMock(content=b"ok", status_code=200, headers={})
        self.mocks["AsyncClient"].return_value.__aenter__.return_value = async_client_instance

    def tearDown(self):
        for p in self.patches.values():
            p.stop()
        self.env.stop()

    def test_invalid_path_rejected(self):
        resp = self.client.get("/..%2Fetc/passwd", headers={"X-API-Key": "tok"})
        self.assertEqual(resp.status_code, 400)

    def test_valid_path_proxies(self):
        resp = self.client.get("/api/data", headers={"X-API-Key": "tok"})
        self.assertEqual(resp.status_code, 200)
        called_url = self.mocks["AsyncClient"].return_value.__aenter__.return_value.request.call_args[0][1]
        self.assertEqual(called_url, "http://example.com/api/data")


if __name__ == "__main__":
    unittest.main()
