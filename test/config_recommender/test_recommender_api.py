import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.config_recommender import recommender_api


class TestConfigRecommender(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(recommender_api.app)

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


if __name__ == "__main__":
    unittest.main()
