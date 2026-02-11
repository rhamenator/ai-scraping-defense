import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.util import cdn_manager


class TestCdnManager(unittest.IsolatedAsyncioTestCase):
    async def test_purge_cache_disabled(self):
        with patch.dict("os.environ", {"ENABLE_GLOBAL_CDN": "false"}, clear=False):
            result = await cdn_manager.purge_cache()
        self.assertFalse(result)

    async def test_purge_cache_requires_zone_or_explicit_url(self):
        with patch.dict(
            "os.environ",
            {
                "ENABLE_GLOBAL_CDN": "true",
                "CLOUD_CDN_PROVIDER": "cloudflare",
                "CLOUD_CDN_API_TOKEN": "token",
                "CLOUD_CDN_ZONE_ID": "",
                "CDN_PURGE_URL": "",
            },
            clear=False,
        ):
            result = await cdn_manager.purge_cache()
        self.assertFalse(result)

    async def test_purge_cache_cloudflare_success(self):
        fake_response = MagicMock()
        fake_response.raise_for_status.return_value = None

        with patch.dict(
            "os.environ",
            {
                "ENABLE_GLOBAL_CDN": "true",
                "CLOUD_CDN_PROVIDER": "cloudflare",
                "CLOUD_CDN_API_TOKEN": "token",
                "CLOUD_CDN_ZONE_ID": "zone-id",
            },
            clear=False,
        ), patch("src.util.cdn_manager.httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            client_instance.__aenter__.return_value.post.return_value = fake_response
            mock_client.return_value = client_instance

            result = await cdn_manager.purge_cache()

        self.assertTrue(result)
        client_instance.__aenter__.return_value.post.assert_awaited_once()
