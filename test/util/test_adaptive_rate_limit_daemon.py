import unittest
from unittest.mock import patch

from src.util import adaptive_rate_limit_daemon as daemon


class TestAdaptiveRateLimitDaemon(unittest.IsolatedAsyncioTestCase):
    async def test_new_limit_updates_immediately(self):
        with patch(
            "src.util.adaptive_rate_limit_daemon.adaptive_rate_limit_manager.update_rate_limit"
        ) as update_limit:
            with patch(
                "src.util.adaptive_rate_limit_daemon.adaptive_rate_limit_manager.compute_and_update"
            ) as compute:
                await daemon.handle_rate_limit_event({"new_limit": 120})
        update_limit.assert_called_once_with(120)
        compute.assert_not_called()

    async def test_config_update_triggers_recompute(self):
        with patch(
            "src.util.adaptive_rate_limit_daemon.adaptive_rate_limit_manager.compute_and_update"
        ) as compute:
            await daemon.handle_rate_limit_event(
                {"base_rate_limit": 40, "window_seconds": 120}
            )
        compute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
