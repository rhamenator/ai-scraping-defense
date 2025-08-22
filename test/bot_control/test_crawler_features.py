import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException, status
from redis.exceptions import RedisError

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
                self.ttl = {}

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

            def expire(self, name, ttl):
                self.ttl[name] = ttl

        mock_redis = MockRedis()
        with patch(
            "src.bot_control.crawler_auth.get_redis_connection", return_value=mock_redis
        ), patch(
            "src.bot_control.pricing.get_redis_connection", return_value=mock_redis
        ):
            self.assertTrue(register_crawler("testbot", "token123", "training"))
            self.assertTrue(verify_crawler("token123"))
            self.assertTrue(verify_crawler("token123", "training"))
            info = get_crawler_info("token123")
            self.assertEqual(info["name"], "testbot")

            set_price("training", 0.01)
            charge = record_crawl("token123", "training")
            self.assertEqual(charge, 0.01)
            self.assertAlmostEqual(get_usage("token123"), 0.01)

    def test_register_crawler_tolerates_expire_failure(self):
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

            def expire(self, name, ttl):
                raise RedisError("fail")

        mock_redis = MockRedis()
        with patch(
            "src.bot_control.crawler_auth.get_redis_connection", return_value=mock_redis
        ):
            # Should still return True even if expiration cannot be set
            self.assertTrue(register_crawler("bot", "tok", "purpose"))
            # And the token should be considered registered
            self.assertTrue(verify_crawler("tok"))

    def test_pricing_handles_redis_unavailable(self):
        with patch("src.bot_control.pricing.get_redis_connection", return_value=None):
            self.assertEqual(record_crawl("tok", "purpose"), 0.001)
            with self.assertRaises(HTTPException) as exc:
                set_price("purpose", 0.1)
            self.assertEqual(
                exc.exception.status_code, status.HTTP_503_SERVICE_UNAVAILABLE
            )
            with self.assertRaises(HTTPException) as exc2:
                get_usage("tok")
            self.assertEqual(
                exc2.exception.status_code, status.HTTP_503_SERVICE_UNAVAILABLE
            )

    def test_record_crawl_returns_default_when_usage_fails(self):
        class MockRedis:
            def hget(self, name, field):
                return "0.1"

            def hincrbyfloat(self, name, field, amount):
                raise RedisError("fail")

        mock_redis = MockRedis()
        with patch(
            "src.bot_control.pricing.get_redis_connection", return_value=mock_redis
        ):
            self.assertEqual(record_crawl("tok", "purpose"), 0.001)

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
