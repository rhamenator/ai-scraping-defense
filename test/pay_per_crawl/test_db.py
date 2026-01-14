import os
import sqlite3
import tempfile
import unittest
import gc
from typing import Dict, Optional

from src.pay_per_crawl import db


class TestCrawlerDB(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "crawler.db")
        os.environ["CRAWLER_DB_PATH"] = self.db_path

    def tearDown(self) -> None:
        try:
            conn = db._get_conn()
        except RuntimeError:
            conn = None
        if conn is not None:
            try:
                conn.close()
            finally:
                db._CONNECTION = None
        gc.collect()
        self.tmpdir.cleanup()
        os.environ.pop("CRAWLER_DB_PATH", None)

    def _balance(self, token: str) -> Optional[float]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT balance FROM crawlers WHERE token=?", (token,))
            row = cur.fetchone()
            return row[0] if row else None

    def test_register_and_get(self) -> None:
        db.init_db(self.db_path)
        db.register_crawler("bot", "tok", "crawl")
        info: Optional[Dict[str, str]] = db.get_crawler("tok")
        self.assertIsNotNone(info)
        self.assertEqual(info["name"], "bot")
        self.assertEqual(info["purpose"], "crawl")
        self.assertEqual(self._balance("tok"), 0)

    def test_add_credit_and_charge(self) -> None:
        db.init_db(self.db_path)
        db.register_crawler("bot", "tok", "crawl")
        db.add_credit("tok", 2.0)
        self.assertTrue(db.charge("tok", 1.5))
        self.assertEqual(self._balance("tok"), 0.5)
        self.assertFalse(db.charge("tok", 1.0))

    def test_get_crawler_missing(self) -> None:
        db.init_db(self.db_path)
        info: Optional[Dict[str, str]] = db.get_crawler("nope")
        self.assertIsNone(info)


if __name__ == "__main__":
    unittest.main()
