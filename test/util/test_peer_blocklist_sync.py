import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from src.util import peer_blocklist_sync as sync

class TestPeerBlocklistSync(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_peer_ips_list_format(self):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = ["1.1.1.1", "2.2.2.2"]
        mock_resp.raise_for_status.return_value = None
        mock_client.__aenter__.return_value.get.return_value = mock_resp
        with patch("src.util.peer_blocklist_sync.httpx.AsyncClient", return_value=mock_client):
            ips = await sync.fetch_peer_ips("http://example.com/list")
        self.assertEqual(ips, ["1.1.1.1", "2.2.2.2"])

    async def test_fetch_peer_ips_dict_format(self):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ips": ["3.3.3.3"]}
        mock_resp.raise_for_status.return_value = None
        mock_client.__aenter__.return_value.get.return_value = mock_resp
        with patch("src.util.peer_blocklist_sync.httpx.AsyncClient", return_value=mock_client):
            ips = await sync.fetch_peer_ips("http://example.com/list")
        self.assertEqual(ips, ["3.3.3.3"])

    async def test_sync_peer_blocklists_updates_redis(self):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = ["4.4.4.4"]
        mock_resp.raise_for_status.return_value = None
        mock_client.__aenter__.return_value.get.return_value = mock_resp
        mock_redis = MagicMock()
        with patch("src.util.peer_blocklist_sync.httpx.AsyncClient", return_value=mock_client), \
             patch("src.util.peer_blocklist_sync.get_redis_connection", return_value=mock_redis), \
             patch.object(sync, "PEER_BLOCKLIST_URLS", "http://peer/list"):
            result = await sync.sync_peer_blocklists()
        mock_redis.setex.assert_called_once()
        self.assertEqual(result, 1)

if __name__ == '__main__':
    unittest.main()
