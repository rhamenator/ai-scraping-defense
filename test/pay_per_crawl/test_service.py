import os
import tempfile
import unittest
from unittest.mock import patch

from src.pay_per_crawl import db, pricing


class TestPayPerCrawlDB(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "crawler.db")
        os.environ["CRAWLER_DB_PATH"] = self.db_path

    def tearDown(self):
        try:
            conn = db._get_conn()
        except RuntimeError:
            conn = None
        if conn is not None:
            try:
                conn.close()
            finally:
                db._CONNECTION = None
        self.tmpdir.cleanup()
        os.environ.pop("CRAWLER_DB_PATH", None)

    def test_register_and_charge(self):
        db.init_db(self.db_path)
        db.register_crawler("bot", "token", "training")
        db.add_credit("token", 1.0)
        info = db.get_crawler("token")
        self.assertAlmostEqual(info["balance"], 1.0)
        self.assertTrue(db.charge("token", 0.5))
        info = db.get_crawler("token")
        self.assertAlmostEqual(info["balance"], 0.5)

    def test_charge_is_atomic_and_cannot_overdraw(self):
        db.init_db(self.db_path)
        db.register_crawler("bot", "token", "training")
        self.assertTrue(db.add_credit("token", 1.0))
        self.assertFalse(db.charge("token", 1.5))
        self.assertAlmostEqual(db.get_crawler("token")["balance"], 1.0)

    def test_financial_audit_does_not_persist_raw_crawler_token(self):
        db.init_db(self.db_path)
        with patch(
            "src.pay_per_crawl.db.blockchain.log_action", return_value=True
        ) as log:
            db.register_crawler("bot", "secret-token", "training")

        payload = log.call_args.args[1]
        self.assertNotIn("token", payload)
        self.assertNotIn("secret-token", payload.values())
        self.assertIn("token_hash", payload)


class TestPricingEngine(unittest.TestCase):
    def test_price_lookup(self):
        engine = pricing.PricingEngine({"docs/": 0.5}, default_price=0.1)
        self.assertEqual(engine.price_for_path("docs/index"), 0.5)
        self.assertEqual(engine.price_for_path("other"), 0.1)


if __name__ == "__main__":
    unittest.main()
