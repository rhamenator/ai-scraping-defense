import importlib.util
import os
import sys
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


if __name__ == "__main__":
    unittest.main()
