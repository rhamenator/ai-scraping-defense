import unittest
from unittest.mock import patch
import datetime

from src.escalation import escalation_engine as ee


class TestExtractFeatures(unittest.TestCase):
    def test_extract_features_basic(self):
        log = {
            "user_agent": "Python-requests/2.0",
            "referer": "",
            "path": "/wp-admin",
            "method": "POST",
            "timestamp": "2023-01-01T12:00:00Z",
        }
        freq = {"count": 5, "time_since": 0.1}
        with (
            patch.object(ee, "is_path_disallowed", return_value=True),
            patch.object(ee, "UA_PARSER_AVAILABLE", False),
            patch.object(ee, "get_country_code", return_value="US"),
        ):
            feats = ee.extract_features(log, freq)
        self.assertEqual(feats["ua_length"], len("Python-requests/2.0"))
        self.assertEqual(feats["path_is_wp"], 1)
        self.assertEqual(feats["path_disallowed"], 1)
        key = f"req_freq_{ee.FREQUENCY_WINDOW_SECONDS}s"
        self.assertEqual(feats[key], 5)
        self.assertEqual(feats["time_since_last_sec"], 0.1)
        self.assertEqual(feats["http_method"], "POST")
        self.assertEqual(feats["hour_of_day"], 12)
        self.assertEqual(feats["day_of_week"], 6)  # 2023-01-01 is Sunday
        self.assertEqual(feats["country_code"], "US")


if __name__ == "__main__":
    unittest.main()
