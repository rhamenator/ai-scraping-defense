import logging
import unittest
from unittest.mock import patch

import src.shared.utils as utils


class TestUtils(unittest.TestCase):

    def setUp(self):
        self.log_file = "test.log"

    def tearDown(self):
        try:
            import os

            logger_inst = utils._event_loggers.pop(self.log_file, None)
            if logger_inst:
                for handler in list(logger_inst.handlers):
                    handler.close()
                    logger_inst.removeHandler(handler)
            os.remove(self.log_file)
        except FileNotFoundError:
            pass

    def test_log_error(self):
        utils.log_error("Test error message", log_file=self.log_file)
        with open(self.log_file, "r") as f:
            content = f.read()
            self.assertIn("Test error message", content)
            self.assertIn("ERROR", content)

    def test_log_event(self):
        event_data = {"key": "value"}
        utils.log_event(self.log_file, "test_event", event_data)
        with open(self.log_file, "r") as f:
            content = f.read()
            self.assertIn("test_event", content)
            self.assertIn("value", content)

    @patch("src.shared.utils.random.random")
    @patch("src.shared.utils.time.sleep", return_value=None)
    def test_inject_failure(self, mock_sleep, mock_random):
        mock_random.return_value = 0.0  # Always trigger failure
        with self.assertRaises(Exception) as context:
            utils.inject_failure(0.9)
        self.assertEqual(
            str(context.exception), "Injected failure for resilience testing"
        )

        mock_random.return_value = 1.0  # Never trigger failure
        try:
            utils.inject_failure(0.9)
        except Exception:
            self.fail("inject_failure raised Exception unexpectedly")


if __name__ == "__main__":
    unittest.main()
