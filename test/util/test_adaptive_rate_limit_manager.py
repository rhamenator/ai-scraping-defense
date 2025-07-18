import unittest
from unittest.mock import MagicMock, patch
import tempfile
import os

from src.util import adaptive_rate_limit_manager as manager

class TestAdaptiveRateLimitManager(unittest.TestCase):
    def test_get_recent_counts(self):
        redis = MagicMock()
        redis.keys.return_value = ["freq:1", "freq:2"]
        redis.zcount.side_effect = [5, 8]
        counts = manager.get_recent_counts(redis, 60)
        self.assertEqual(counts, [5, 8])

    def test_compute_and_update(self):
        mock_redis = MagicMock()
        with (
            patch.object(manager, "get_recent_counts", return_value=[10, 20]) as grc,
            patch("src.util.adaptive_rate_limit_manager.compute_rate_limit", return_value=40) as comp,
            patch.object(manager, "update_rate_limit") as upd,
        ):
            result = manager.compute_and_update(mock_redis)
        grc.assert_called_once_with(mock_redis, manager.FREQUENCY_WINDOW_SECONDS)
        comp.assert_called_once_with([10, 20], manager.BASE_RATE_LIMIT)
        upd.assert_called_once_with(40)
        self.assertEqual(result, 40)

    def test_update_rate_limit_writes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "rate.conf")
            with patch.object(manager, "NGINX_RATE_LIMIT_CONF", path):
                self.assertTrue(manager.update_rate_limit(70))
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
        self.assertEqual(
            content,
            "limit_req_zone $binary_remote_addr zone=req_rate_limit:10m rate=70r/m;",
        )

if __name__ == "__main__":
    unittest.main()
