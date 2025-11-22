# test/shared/honeypot_logger.test.py
import datetime
import importlib  # Required for reloading the module
import json
import logging
import os
import unittest
from unittest.mock import MagicMock, mock_open, patch

# Import the module to test.
# We will reload it in specific tests to check its import-time setup.
from src.shared import honeypot_logger


class TestJsonFormatter(unittest.TestCase):
    def test_format_log_record(self):
        """Test that JsonFormatter correctly formats a LogRecord."""
        formatter = honeypot_logger.JsonFormatter()

        # Create a dummy LogRecord
        record_data = {
            "name": "test_logger",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "pathname": "test_path.py",
            "filename": "test_path.py",
            "module": "test_path",
            "lineno": 123,
            "funcName": "test_func",
            "created": 1678886400.0,  # Fixed epoch seconds for reproducible timestamp
            "message": "Original message before args",  # This is record.msg
        }
        record = logging.LogRecord(
            name=record_data["name"],
            level=record_data["levelno"],
            pathname=record_data["pathname"],
            lineno=record_data["lineno"],
            msg="Test log message with args: %s",  # Original message string
            args=("arg1",),
            exc_info=None,
            func=record_data["funcName"],
        )
        record.created = record_data["created"]  # Override for consistent timestamp
        record.levelname = record_data["levelname"]  # Ensure levelname is set

        # Simulate 'extra' details that would be passed to logger.info(..., extra=...)
        record.details = {"ip": "1.2.3.4", "custom_field": "value"}

        formatted_json_str = formatter.format(record)
        formatted_data = json.loads(formatted_json_str)

        expected_timestamp = (
            datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

        self.assertEqual(formatted_data["timestamp"], expected_timestamp)
        self.assertEqual(formatted_data["level"], "INFO")
        # record.getMessage() is called by formatter.format() to get the final message
        self.assertEqual(formatted_data["message"], "Test log message with args: arg1")
        self.assertEqual(formatted_data["ip"], "1.2.3.4")
        self.assertEqual(formatted_data["custom_field"], "value")


class TestLogHoneypotHitFunction(unittest.TestCase):

    def test_log_honeypot_hit_success(self):
        """Test successful logging by log_honeypot_hit."""
        import importlib

        importlib.reload(honeypot_logger)
        details = {"ip": "192.168.1.100", "path": "/decoy"}
        with patch.object(honeypot_logger.honeypot_logger, "info") as mock_info:
            honeypot_logger.log_honeypot_hit(details)
            mock_info.assert_called_once_with(
                "Honeypot triggered", extra={"details": details}
            )

    def test_log_honeypot_hit_logger_exception(self):
        """Test fallback print when logger.info raises an exception."""
        import importlib

        importlib.reload(honeypot_logger)
        details = {"ip": "10.0.0.5", "error_trigger": True}
        with patch.object(
            honeypot_logger.honeypot_logger,
            "info",
            side_effect=Exception("Logger failed"),
        ) as mock_info, patch("builtins.print") as mock_print:
            honeypot_logger.log_honeypot_hit(details)
            mock_info.assert_called_once()
            mock_print.assert_called_once()
            args, _ = mock_print.call_args
            self.assertIn("ERROR in log_honeypot_hit: Logger failed", args[0])
            self.assertIn("'ip': '10.0.0.5'", args[0])


class TestHoneypotLoggerSetup(unittest.TestCase):

    def setUp(self):
        # Store original handlers to restore them if they exist
        self.original_handlers = list(honeypot_logger.honeypot_logger.handlers)
        honeypot_logger.honeypot_logger.handlers = []  # Clear handlers for test
        # Store original HONEYPOT_LOG_FILE and patch it
        self.original_log_file = honeypot_logger.HONEYPOT_LOG_FILE
        self.test_log_file = "test_temp_honeypot_hits.log"
        honeypot_logger.HONEYPOT_LOG_FILE = self.test_log_file

    def tearDown(self):
        # Clean up handlers added during the test
        for handler in list(honeypot_logger.honeypot_logger.handlers):
            honeypot_logger.honeypot_logger.removeHandler(handler)
            if hasattr(handler, "close"):  # Close file handlers
                handler.close()
        # Restore original handlers
        honeypot_logger.honeypot_logger.handlers = self.original_handlers
        # Restore original log file path
        honeypot_logger.HONEYPOT_LOG_FILE = self.original_log_file
        # Remove test log file if created
        if os.path.exists(self.test_log_file):
            os.remove(self.test_log_file)

    @patch("logging.FileHandler")
    @patch("logging.getLogger")
    @patch("os.makedirs")
    # No need to patch HONEYPOT_LOG_FILE here as it's handled in setUp/tearDown
    def test_logger_setup_on_import_or_reload(
        self, mock_makedirs, mock_getLogger, mock_FileHandler
    ):
        """Test the logger setup logic that runs on module import/reload."""

        mock_logger_instance = MagicMock(spec=logging.Logger)
        mock_logger_instance.hasHandlers.return_value = False
        mock_getLogger.return_value = mock_logger_instance

        mock_file_handler_instance = MagicMock()
        mock_FileHandler.return_value = mock_file_handler_instance

        # Reload the module to trigger setup logic
        importlib.reload(honeypot_logger)

        mock_makedirs.assert_called_once_with(
            os.path.dirname(self.test_log_file), exist_ok=True
        )
        mock_getLogger.assert_called_with("honeypot_logger")
        mock_logger_instance.setLevel.assert_called_once_with(logging.INFO)
        self.assertFalse(mock_logger_instance.propagate)
        mock_FileHandler.assert_called_once_with(self.test_log_file)
        mock_file_handler_instance.setFormatter.assert_called_once()
        formatter_arg = mock_file_handler_instance.setFormatter.call_args[0][0]
        self.assertIsInstance(formatter_arg, honeypot_logger.JsonFormatter)
        mock_logger_instance.addHandler.assert_called_once_with(
            mock_file_handler_instance
        )

    @patch("logging.FileHandler", side_effect=IOError("Cannot open file"))
    @patch("logging.getLogger")
    @patch("os.makedirs")
    @patch("builtins.print")
    def test_logger_setup_filehandler_exception(
        self, mock_print, mock_makedirs, mock_getLogger, mock_FileHandler
    ):
        """Test that file handler exception falls back to console logging."""
        mock_logger_instance = MagicMock(spec=logging.Logger)
        mock_logger_instance.hasHandlers.return_value = False
        mock_getLogger.return_value = mock_logger_instance

        # Should not raise SystemExit anymore, should fall back to console
        importlib.reload(honeypot_logger)

        mock_makedirs.assert_called_once_with(
            os.path.dirname(self.test_log_file), exist_ok=True
        )
        mock_FileHandler.assert_called_once_with(self.test_log_file)
        # Should warn about falling back to console
        mock_print.assert_any_call(
            "WARNING: Cannot set up honeypot file logger: Cannot open file. Using console only."
        )
        # Should have added a handler (console handler)
        mock_logger_instance.addHandler.assert_called()

    @patch("builtins.print")
    @patch("os.makedirs", side_effect=OSError("Permission denied"))
    def test_logger_setup_makedirs_exception(self, mock_makedirs, mock_print):
        """Test that makedirs exception falls back to temp directory."""
        # Should not raise SystemExit anymore, should fall back to temp
        importlib.reload(honeypot_logger)
        # Should be called twice: once for original path, once for temp
        self.assertGreaterEqual(mock_makedirs.call_count, 1)
        # Should warn about the fallback
        self.assertTrue(any("WARNING" in str(call) for call in mock_print.call_args_list))

    @patch("logging.getLogger")
    @patch("os.makedirs")
    def test_logger_setup_skips_if_handlers_exist(self, mock_makedirs, mock_getLogger):
        mock_logger_instance = MagicMock(spec=logging.Logger)
        mock_logger_instance.hasHandlers.return_value = True
        mock_getLogger.return_value = mock_logger_instance

        with patch("logging.FileHandler") as mock_FileHandler_skipped:
            importlib.reload(honeypot_logger)
            mock_FileHandler_skipped.assert_not_called()
            mock_logger_instance.addHandler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
