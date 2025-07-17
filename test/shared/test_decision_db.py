# test/shared/decision_db.test.py
import unittest
import os
import sqlite3
import importlib
from unittest.mock import patch

from src.shared import decision_db

class TestRecordDecision(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory and database path
        self.test_dir = os.path.dirname(__file__)
        self.temp_db = os.path.join(self.test_dir, 'temp_decisions.db')
        # Ensure cleanup of old file
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)

    def tearDown(self):
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)

    def reload_module_with_temp_db(self):
        with patch.dict(os.environ, {'DECISIONS_DB_PATH': self.temp_db}):
            return importlib.reload(decision_db)

    def test_creates_table_and_inserts_record(self):
        db_module = self.reload_module_with_temp_db()

        # Call record_decision to create database and insert a row
        db_module.record_decision('1.2.3.4', 'unit_test', 0.9, 1, 'block', '2024-01-01T00:00:00Z')

        # Verify the database file now exists
        self.assertTrue(os.path.exists(self.temp_db))

        # Read back the inserted row directly using sqlite3
        conn = sqlite3.connect(self.temp_db)
        try:
            cur = conn.cursor()
            cur.execute("SELECT ip, source, score, is_bot, action, timestamp FROM decisions")
            row = cur.fetchone()
        finally:
            conn.close()

        self.assertEqual(row, ('1.2.3.4', 'unit_test', 0.9, 1, 'block', '2024-01-01T00:00:00Z'))

    def test_handles_none_is_bot(self):
        db_module = self.reload_module_with_temp_db()

        db_module.record_decision('5.6.7.8', 'unit_test', 0.1, None, 'allow', '2024-02-02T00:00:00Z')

        conn = sqlite3.connect(self.temp_db)
        try:
            cur = conn.cursor()
            cur.execute("SELECT is_bot FROM decisions")
            (value,) = cur.fetchone()
        finally:
            conn.close()

        self.assertIsNone(value)

if __name__ == '__main__':
    unittest.main()
