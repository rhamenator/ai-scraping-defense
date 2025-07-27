import importlib.util
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

MODULE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "prompt-router", "main.py")
)

spec = importlib.util.spec_from_file_location("prompt_router.main", MODULE_PATH)
pr_module = importlib.util.module_from_spec(spec)
sys.modules["prompt_router.main"] = pr_module
spec.loader.exec_module(pr_module)
app = pr_module.app


class TestRoutingBehavior(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "MAX_LOCAL_TOKENS": "5",
                "LOCAL_LLM_URL": "http://local",
                "CLOUD_PROXY_URL": "http://cloud",
            },
        )
        self.env.start()
        spec.loader.exec_module(pr_module)
        global app
        app = pr_module.app

    def tearDown(self):
        self.env.stop()

    async def _send_prompt(self, prompt: str):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"route": "ok"}
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        calls = []

        async def dummy_post(url, json, timeout):
            calls.append((url, json, timeout))
            return mock_resp

        async_client = AsyncMock()
        async_client.__aenter__.return_value = async_client
        async_client.post.side_effect = dummy_post

        with patch.object(pr_module, "httpx") as httpx_mod:
            httpx_mod.AsyncClient.return_value = async_client
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
                await ac.post("/route", json={"prompt": prompt})
        return calls

    async def test_short_prompt_goes_local(self):
        calls = await self._send_prompt("hi")
        self.assertEqual(calls[0][0], "http://local")

    async def test_long_prompt_goes_cloud(self):
        calls = await self._send_prompt("x" * 10)
        self.assertEqual(calls[0][0], "http://cloud")


if __name__ == "__main__":
    unittest.main()
