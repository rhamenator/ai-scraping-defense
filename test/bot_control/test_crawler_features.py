import unittest

from src.bot_control.crawler_auth import register_crawler, verify_crawler, get_crawler_info
from src.bot_control.pricing import set_price, record_crawl, get_usage
from src.tarpit.labyrinth import generate_labyrinth_page
from src.security.risk_scoring import RiskScorer
from src.security.attack_score import compute_attack_score


class TestCrawlerFeatures(unittest.TestCase):
    def test_crawler_registration_and_usage(self):
        register_crawler("testbot", "token123", "training")
        self.assertTrue(verify_crawler("token123"))
        self.assertTrue(verify_crawler("token123", "training"))
        info = get_crawler_info("token123")
        self.assertEqual(info["name"], "testbot")

        set_price("training", 0.01)
        charge = record_crawl("token123", "training")
        self.assertEqual(charge, 0.01)
        self.assertAlmostEqual(get_usage("token123"), 0.01)

    def test_labyrinth_generation(self):
        html = generate_labyrinth_page("seed", depth=3)
        self.assertIn("/tarpit/", html)

    def test_risk_and_attack_scores(self):
        scorer = RiskScorer()
        r = scorer.score({"is_vpn": 1, "high_freq": 1, "anomaly_score": 0.8})
        self.assertGreater(r, 0.5)
        a = compute_attack_score("SELECT * FROM users WHERE id=1 --")
        self.assertGreaterEqual(a, 0.7)


if __name__ == "__main__":
    unittest.main()
