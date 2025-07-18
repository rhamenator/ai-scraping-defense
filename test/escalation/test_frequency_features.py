import unittest
from unittest.mock import MagicMock, patch

from src.escalation import escalation_engine as ee

class TestFrequencyFeatures(unittest.TestCase):
    def test_get_realtime_frequency_features_py(self):
        mock_redis = MagicMock()
        pipe = mock_redis.pipeline.return_value
        pipe.execute.return_value = [None, None, 3, [(b"1", 1000.0), (b"2", 1001.0)], True]
        with patch.object(ee, "redis_client_freq", mock_redis), patch.object(ee, "FREQUENCY_TRACKING_ENABLED", True), patch("time.time", return_value=1002.0):
            feats = ee._get_realtime_frequency_features_py("1.1.1.1")
        self.assertEqual(feats["count"], 2)
        self.assertAlmostEqual(feats["time_since"], 2.0, places=2)

if __name__ == "__main__":
    unittest.main()
