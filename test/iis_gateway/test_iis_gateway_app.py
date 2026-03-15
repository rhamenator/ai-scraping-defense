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
        self.redis_mock.get.return_value = None
        self.redis_mock.ttl.return_value = 60

        self.escalate_patch = patch("src.iis_gateway.main.escalate", new=AsyncMock())
        self.escalate_patch.start()

        async_client_instance = AsyncMock()
        async_client_instance.request.return_value = MagicMock(
            content=b"ok", status_code=200, headers={}
        )
        self.async_client_instance = async_client_instance
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

    def test_throttled_ip_returns_retry_after(self):
        self.redis_mock.exists.return_value = False
        self.redis_mock.get.return_value = '{"rate_limit_per_minute": 1}'
        self.redis_mock.ttl.side_effect = [33, 33]
        self.redis_mock.incr.return_value = 2
        self.redis_mock.expire.return_value = True

        resp = self.client.get("/throttled")

        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.headers["retry-after"], "33")

    def test_throttle_uses_override_limit_without_hard_deny(self):
        self.redis_mock.exists.return_value = False
        self.redis_mock.get.return_value = '{"rate_limit_per_minute": 3}'
        self.redis_mock.ttl.return_value = 45
        self.redis_mock.incr.side_effect = [1, 2, 3, 4]
        self.redis_mock.expire.return_value = True

        with patch.object(self.gateway.settings, "RATE_LIMIT_PER_MINUTE", 0):
            self.assertEqual(self.client.get("/limited").status_code, 200)
            self.assertEqual(self.client.get("/limited").status_code, 200)
            self.assertEqual(self.client.get("/limited").status_code, 200)
            resp = self.client.get("/limited")

        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.headers["retry-after"], "45")

    def test_throttle_lookup_redis_error_returns_503(self):
        self.redis_mock.exists.return_value = False
        self.redis_mock.get.side_effect = self.gateway.RedisError("boom")

        resp = self.client.get("/throttle-error")

        self.assertEqual(resp.status_code, 503)

    def test_proxy_sanitizes_spoofed_forward_headers(self):
        self.redis_mock.exists.return_value = False
        self.redis_mock.incr.return_value = 1
        self.redis_mock.expire.return_value = True

        response = self.client.get(
            "/proxy-target",
            headers={
                "Host": "public.example",
                "X-Forwarded-For": "8.8.8.8",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "spoofed.example",
                "X-Forwarded-Port": "443",
                "X-Real-IP": "7.7.7.7",
            },
        )

        self.assertEqual(response.status_code, 200)
        request_call = self.async_client_instance.request.await_args
        forwarded_headers = request_call.kwargs["headers"]
        self.assertEqual(forwarded_headers["Host"], "public.example")
        self.assertEqual(forwarded_headers["X-Forwarded-Host"], "public.example")
        self.assertEqual(forwarded_headers["X-Forwarded-For"], "testclient")
        self.assertEqual(forwarded_headers["X-Real-IP"], "testclient")
        self.assertEqual(forwarded_headers["X-Forwarded-Proto"], "http")
        self.assertEqual(forwarded_headers["X-Forwarded-Port"], "80")


if __name__ == "__main__":
    unittest.main()
