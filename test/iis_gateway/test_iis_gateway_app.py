import importlib
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestIISGateway(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "BACKEND_URL": "http://example.com",
                "RATE_LIMIT_PER_MINUTE": "1",
            },
        )
        self.env.start()
        import src.iis_gateway.main as gateway

        importlib.reload(gateway)
        self.gateway = gateway
        self.client = TestClient(self.gateway.app)

        self.redis_mock = MagicMock()
        self.gateway.redis_client = self.redis_mock

        self.escalate_patch = patch("src.iis_gateway.main.escalate", new=AsyncMock())
        self.escalate_patch.start()

        async_client_instance = AsyncMock()
        async_client_instance.request.return_value = MagicMock(
            content=b"ok", status_code=200, headers={}
        )
        self.httpx_patch = patch("src.iis_gateway.main.httpx.AsyncClient")
        self.httpx_mock = self.httpx_patch.start()
        self.httpx_mock.return_value.__aenter__.return_value = async_client_instance

    def tearDown(self):
        self.httpx_patch.stop()
        self.escalate_patch.stop()
        self.env.stop()

    def test_rate_limit_exceeded(self):
        self.redis_mock.exists.return_value = False
        self.redis_mock.incr.side_effect = [1, 2]
        self.redis_mock.expire.return_value = True
        self.client.get("/api")
        resp = self.client.get("/api")
        self.assertEqual(resp.status_code, 429)

    def test_blocklist_cache(self):
        self.redis_mock.exists.return_value = True
        resp1 = self.client.get("/blocked")
        resp2 = self.client.get("/blocked")
        self.assertEqual(resp1.status_code, 403)
        self.assertEqual(resp2.status_code, 403)
        self.redis_mock.exists.assert_called_once()


if __name__ == "__main__":
    unittest.main()
