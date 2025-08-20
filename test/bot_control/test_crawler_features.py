import os
import unittest
from unittest.mock import patch

from src.bot_control.crawler_auth import (
    get_crawler_info,
    register_crawler,
    verify_crawler,
)
from src.bot_control.pricing import get_usage, record_crawl, set_price
from src.security.attack_score import compute_attack_score
from src.security.risk_scoring import RiskScorer
from src.tarpit.labyrinth import generate_labyrinth_page


class TestCrawlerFeatures(unittest.TestCase):
    def test_crawler_registration_and_usage(self):
        class MockRedis:
            def __init__(self):
                self.store = {}

            def hset(self, name, key=None, value=None, mapping=None):
                if mapping is not None:
                    self.store.setdefault(name, {}).update(mapping)
                elif key is not None:
                    self.store.setdefault(name, {})[key] = value

            def hgetall(self, name):
                return self.store.get(name, {}).copy()

            def hget(self, name, field):
                return self.store.get(name, {}).get(field)

            def hincrbyfloat(self, name, field, amount):
                current = float(self.store.get(name, {}).get(field, 0)) + amount
                self.store.setdefault(name, {})[field] = current
                return current

        mock_redis = MockRedis()
        with patch(
            "src.bot_control.crawler_auth.get_redis_connection", return_value=mock_redis
        ), patch(
            "src.bot_control.pricing.get_redis_connection", return_value=mock_redis
        ):
            register_crawler("testbot", "token123", "training")
            self.assertTrue(verify_crawler("token123"))
            self.assertTrue(verify_crawler("token123", "training"))
            info = get_crawler_info("token123")
            self.assertEqual(info["name"], "testbot")

            set_price("training", 0.01)
            charge = record_crawl("token123", "training")
            self.assertEqual(charge, 0.01)
            self.assertAlmostEqual(get_usage("token123"), 0.01)

    def test_labyrinth_generation_no_fp(self):
        html = generate_labyrinth_page("seed", depth=3)
        self.assertIn("/tarpit/", html)
        self.assertNotIn("navigator.userAgent", html)

    def test_labyrinth_generation_with_fp(self):
        with patch.dict(os.environ, {"ENABLE_FINGERPRINTING": "true"}):
            html = generate_labyrinth_page("seed", depth=3)
        self.assertIn("navigator.userAgent", html)

    def test_risk_and_attack_scores(self):
        scorer = RiskScorer()
        r = scorer.score({"is_vpn": 1, "high_freq": 1, "anomaly_score": 0.8})
        self.assertGreater(r, 0.5)
        a = compute_attack_score("SELECT * FROM users WHERE id=1 --")
        self.assertGreaterEqual(a, 0.7)


if __name__ == "__main__":
    unittest.main()
