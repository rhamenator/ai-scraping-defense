import os
import tempfile
import unittest

from src.pay_per_crawl import db, pricing


class TestPayPerCrawlDB(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "crawler.db")
        os.environ["CRAWLER_DB_PATH"] = self.db_path
        db.init_db(self.db_path)

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("CRAWLER_DB_PATH", None)

    def test_register_and_charge(self):
        db.register_crawler("bot", "token", "training", self.db_path)
        db.add_credit("token", 1.0, self.db_path)
        info = db.get_crawler("token", self.db_path)
        self.assertAlmostEqual(info["balance"], 1.0)
        self.assertTrue(db.charge("token", 0.5, self.db_path))
        info = db.get_crawler("token", self.db_path)
        self.assertAlmostEqual(info["balance"], 0.5)


class TestPricingEngine(unittest.TestCase):
    def test_price_lookup(self):
        engine = pricing.PricingEngine({"docs/": 0.5}, default_price=0.1)
        self.assertEqual(engine.price_for_path("docs/index"), 0.5)
        self.assertEqual(engine.price_for_path("other"), 0.1)


if __name__ == "__main__":
    unittest.main()
