import json
import os
import tempfile
import unittest
from unittest import mock

from src.pay_per_crawl import blockchain


class TestBlockchainLog(unittest.TestCase):
    def test_hash_chain_and_token_redaction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "blockchain.log")
            with mock.patch.dict(
                os.environ,
                {
                    "PAY_PER_CRAWL_BLOCKCHAIN_LOG_ENABLED": "true",
                    "PAY_PER_CRAWL_BLOCKCHAIN_LOG_PATH": log_path,
                },
                clear=False,
            ):
                # Re-import module-level settings
                blockchain.LOG_ENABLED = True
                blockchain.LOG_PATH = blockchain.Path(log_path)
                blockchain._last_hash = None

                first = blockchain.log_action(
                    "register_crawler", {"token": "tok123", "amount": 10}
                )
                second = blockchain.log_action(
                    "charge", {"token": "tok123", "amount": 1}
                )
                self.assertTrue(first)
                self.assertTrue(second)

                lines = blockchain.LOG_PATH.read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(lines), 2)
                first_payload = json.loads(lines[0])
                second_payload = json.loads(lines[1])
                self.assertEqual(first_payload["hash"], second_payload["prev_hash"])
                self.assertNotIn("token", first_payload["data"])
                self.assertIn("token_hash", first_payload["data"])


if __name__ == "__main__":
    unittest.main()
