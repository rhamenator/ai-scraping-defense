import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.config_recommender import recommender_api


class TestConfigRecommender(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict(
            os.environ, {"RECOMMENDER_API_KEY": "test-secret"}, clear=False
        )
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)
        self.client = TestClient(
            recommender_api.app, headers={"X-API-Key": "test-secret"}
        )

    def test_missing_api_key_configuration_fails_closed(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RECOMMENDER_API_KEY", None)
            response = self.client.get("/recommendations")
        self.assertEqual(response.status_code, 503)

    @patch("src.config_recommender.recommender_api.get_metrics")
    def test_recommendations_generation(self, mock_get_metrics):
        mock_get_metrics.return_value = b"""
http_requests_total{method=\"GET\"} 1000
bots_detected_high_score_total 150
tarpit_entries_total 120
"""
        response = self.client.get("/recommendations")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("recommendations", data)
        recs = data["recommendations"]
        self.assertIn("TAR_PIT_MAX_HOPS", recs)
        self.assertIn("BLOCKLIST_TTL_SECONDS", recs)

    @patch("src.config_recommender.recommender_api.get_metrics")
    def test_cloudflare_attack_mode_is_advisory_and_gated(self, mock_get_metrics):
        mock_get_metrics.return_value = b"""
http_requests_total 1000
bots_detected_total 400
"""
        with patch.dict(
            "os.environ",
            {"ENABLE_GLOBAL_CDN": "true", "CLOUD_CDN_PROVIDER": "cloudflare"},
            clear=False,
        ):
            recs = self.client.get("/recommendations").json()["recommendations"]
        self.assertEqual(recs["CLOUDFLARE_UNDER_ATTACK_MODE"], 1)

        with patch.dict(
            "os.environ",
            {"ENABLE_GLOBAL_CDN": "false", "CLOUD_CDN_PROVIDER": "cloudflare"},
            clear=False,
        ):
            recs = self.client.get("/recommendations").json()["recommendations"]
        self.assertNotIn("CLOUDFLARE_UNDER_ATTACK_MODE", recs)


if __name__ == "__main__":
    unittest.main()
