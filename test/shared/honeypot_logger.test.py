# test\shared\honeypot_logger.test.py
import unittest
from unittest.mock import patch, mock_open, MagicMock
from shared import honeypot_logger
import logging

class TestHoneypotLogger(unittest.TestCase):

    @patch("builtins.open", new_callable=mock_open)
    @patch("logging.FileHandler")
    def test_logger_initialization(self, mock_handler, mock_file):
        logger = honeypot_logger.get_logger("test_logger")
        self.assertTrue(logger.hasHandlers())

    def test_log_entry_structure(self):
        entry = honeypot_logger.format_log_entry(ip="127.0.0.1", url="/trap", threat_level=5)
        self.assertIn("127.0.0.1", entry)
        self.assertIn("/trap", entry)
        self.assertIn("level=5", entry)

    @patch("shared.honeypot_logger.logger")
    def test_log_warning_called(self, mock_logger):
        honeypot_logger.log_warning("/bad", "192.0.2.1", 9)
        mock_logger.warning.assert_called_once()
        args, _ = mock_logger.warning.call_args
        self.assertIn("192.0.2.1", args[0])

if __name__ == '__main__':
    unittest.main()
