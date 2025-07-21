import unittest
from unittest.mock import MagicMock, patch

from src.escalation import escalation_engine as ee
from src.escalation.escalation_engine import RequestMetadata


class TestFingerprinting(unittest.TestCase):
    def test_compute_browser_fingerprint_consistent(self):
        meta = RequestMetadata(
            timestamp="2023-01-01T00:00:00Z",
            ip="1.1.1.1",
            source="test",
            method="GET",
            user_agent="Mozilla/5.0",
            headers={"Accept-Language": "en-US", "Accept": "text/html"},
        )
        fp1 = ee.compute_browser_fingerprint(meta)
        fp2 = ee.compute_browser_fingerprint(meta)
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 64)

    def test_track_fingerprint_updates_redis(self):
        mock_redis = MagicMock()
        with (
            patch.object(ee, "redis_client_fingerprints", mock_redis),
            patch.object(ee, "FINGERPRINT_TRACKING_ENABLED", True),
        ):
            mock_redis.scard.return_value = 2
            count = ee.track_fingerprint("abc", "1.1.1.1")
        mock_redis.sadd.assert_called_once_with("default:fp:abc", "1.1.1.1")
        mock_redis.expire.assert_called_once_with(
            "default:fp:abc", ee.FINGERPRINT_WINDOW_SECONDS
        )
        mock_redis.scard.assert_called_once_with("default:fp:abc")
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
