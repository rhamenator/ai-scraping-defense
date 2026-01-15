import importlib.util
import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

# Dynamically load the prompt router module located in ../../prompt-router/main.py
MODULE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "prompt-router", "main.py")
)
os.environ["SHARED_SECRET"] = "secret"
spec = importlib.util.spec_from_file_location("prompt_router.main", MODULE_PATH)
pr_module = importlib.util.module_from_spec(spec)
sys.modules["prompt_router.main"] = pr_module
spec.loader.exec_module(pr_module)
app = pr_module.app


class TestPromptRouterRouting(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Use small token limit for predictable routing
        self.env = patch.dict(
            os.environ,
            {
                "MAX_LOCAL_TOKENS": "10",
                "LOCAL_LLM_URL": "http://local",
                "CLOUD_PROXY_URL": "http://cloud",
                "SHARED_SECRET": "secret",
            },
        )
        self.env.start()
        # Re-execute the module so constants pick up patched environment
        spec.loader.exec_module(pr_module)
        global app
        app = pr_module.app

    def tearDown(self):
        self.env.stop()

    async def test_short_prompt_routes_locally(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"route": "local"}
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None

        class DummyClient:
            instances = []

            def __init__(self, *args, **kwargs):
                self.post_calls = []
                DummyClient.instances.append(self)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                pass

            async def post(self, url, json, timeout):
                self.post_calls.append((url, json, timeout))
                return mock_resp

        with patch.object(pr_module, "httpx") as httpx_mod:
            httpx_mod.AsyncClient = DummyClient
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    "/route",
                    json={"prompt": "short"},
                    headers={"Authorization": "Bearer secret"},
                )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"route": "local"})
        client_inst = DummyClient.instances[-1]
        self.assertIn("http://local", [c[0] for c in client_inst.post_calls])

    async def test_long_prompt_routes_to_cloud(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"route": "cloud"}
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None

        class DummyClient:
            instances = []

            def __init__(self, *args, **kwargs):
                self.post_calls = []
                DummyClient.instances.append(self)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                pass

            async def post(self, url, json, timeout):
                self.post_calls.append((url, json, timeout))
                return mock_resp

        with patch.object(pr_module, "httpx") as httpx_mod:
            httpx_mod.AsyncClient = DummyClient
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as ac:
                long_prompt = " ".join(["x"] * 20)
                resp = await ac.post(
                    "/route",
                    json={"prompt": long_prompt},
                    headers={"Authorization": "Bearer secret"},
                )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"route": "cloud"})
        client_inst = DummyClient.instances[-1]
        self.assertIn("http://cloud", [c[0] for c in client_inst.post_calls])


class TestAuthAndRateLimit(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "MAX_LOCAL_TOKENS": "10",
                "LOCAL_LLM_URL": "http://local",
                "CLOUD_PROXY_URL": "http://cloud",
                "SHARED_SECRET": "secret",
                "RATE_LIMIT_REQUESTS": "2",
                "RATE_LIMIT_WINDOW": "10",
                "TRUST_PROXY_HEADERS": "false",
            },
        )
        self.env.start()
        spec.loader.exec_module(pr_module)
        global app
        app = pr_module.app

    def tearDown(self):
        self.env.stop()

    async def _post(self, headers=None, json=None):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None

        async_client = AsyncMock()
        async_client.__aenter__.return_value = async_client
        async_client.post.return_value = mock_resp

        with patch.object(pr_module, "httpx") as httpx_mod:
            httpx_mod.AsyncClient.return_value = async_client
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as ac:
                return await ac.post(
                    "/route", json=json or {"prompt": "hi"}, headers=headers or {}
                )

    async def test_missing_auth_returns_401(self):
        resp = await self._post()
        self.assertEqual(resp.status_code, 401)

    async def test_rate_limit_headers_and_429(self):
        headers = {"Authorization": "Bearer secret"}
        resp1 = await self._post(headers=headers)
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.headers["X-RateLimit-Limit"], "2")
        self.assertEqual(resp1.headers["X-RateLimit-Remaining"], "1")
        resp2 = await self._post(headers=headers)
        self.assertEqual(resp2.status_code, 200)
        resp3 = await self._post(headers=headers)
        self.assertEqual(resp3.status_code, 429)
        self.assertEqual(resp3.headers["X-RateLimit-Remaining"], "0")
        self.assertIn("Retry-After", resp3.headers)

    async def test_window_rollover_resets_counter(self):
        headers = {"Authorization": "Bearer secret"}
        real_time = time.time

        class FakeTime:
            def __init__(self, values):
                self.values = iter(values)

            def time(self):
                try:
                    return next(self.values)
                except StopIteration:
                    return real_time()

        with patch.object(pr_module, "time", FakeTime([0, 11])):
            resp1 = await self._post(headers=headers)
            self.assertEqual(resp1.status_code, 200)
            resp2 = await self._post(headers=headers)
            self.assertEqual(resp2.status_code, 200)

    async def test_proxy_headers_ignored_by_default(self):
        with patch.dict(os.environ, {"RATE_LIMIT_REQUESTS": "1"}):
            spec.loader.exec_module(pr_module)
            global app
            app = pr_module.app
            headers1 = {"Authorization": "Bearer secret", "X-Forwarded-For": "1.1.1.1"}
            resp1 = await self._post(headers=headers1)
            self.assertEqual(resp1.status_code, 200)
            headers2 = {"Authorization": "Bearer secret", "X-Forwarded-For": "2.2.2.2"}
            resp2 = await self._post(headers=headers2)
            self.assertEqual(resp2.status_code, 429)

    async def test_proxy_headers_used_when_trusted(self):
        with patch.dict(
            os.environ, {"TRUST_PROXY_HEADERS": "true", "RATE_LIMIT_REQUESTS": "1"}
        ):
            spec.loader.exec_module(pr_module)
            global app
            app = pr_module.app
            resp1 = await self._post(
                headers={"Authorization": "Bearer secret", "X-Forwarded-For": "1.1.1.1"}
            )
            resp2 = await self._post(
                headers={"Authorization": "Bearer secret", "X-Forwarded-For": "2.2.2.2"}
            )
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)

    async def test_cleanup_removes_old_ips(self):
        with patch.dict(
            os.environ, {"TRUST_PROXY_HEADERS": "true", "RATE_LIMIT_REQUESTS": "1"}
        ):
            spec.loader.exec_module(pr_module)
            global app
            app = pr_module.app
            real_time = time.time

            class FakeTime:
                def __init__(self, values):
                    self.values = iter(values)

                def time(self):
                    try:
                        return next(self.values)
                    except StopIteration:
                        return real_time()

            with patch.object(pr_module, "time", FakeTime([0, 11])):
                await self._post(
                    headers={
                        "Authorization": "Bearer secret",
                        "X-Forwarded-For": "1.1.1.1",
                    }
                )
                await self._post(
                    headers={
                        "Authorization": "Bearer secret",
                        "X-Forwarded-For": "2.2.2.2",
                    }
                )
        self.assertNotIn("1.1.1.1", pr_module._request_counts)


if __name__ == "__main__":
    unittest.main()
