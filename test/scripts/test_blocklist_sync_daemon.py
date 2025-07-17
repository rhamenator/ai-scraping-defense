import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from scripts import blocklist_sync_daemon

class TestBlocklistSyncDaemon(unittest.IsolatedAsyncioTestCase):
    async def test_run_sync_loop_runs_task(self):
        stop_event = asyncio.Event()
        async_mock = AsyncMock()
        async def stop_soon():
            await asyncio.sleep(0.01)
            stop_event.set()
        with patch('scripts.blocklist_sync_daemon.community_blocklist_sync.sync_blocklist', async_mock):
            asyncio.create_task(stop_soon())
            await blocklist_sync_daemon.run_sync_loop(stop_event)
        async_mock.assert_called()

if __name__ == '__main__':
    unittest.main()
