# test/shared/honeypot_logger.test.py
import unittest
from unittest.mock import patch, MagicMock, mock_open
import logging
import json
import datetime
import os
import importlib # Required for reloading the module

# Import the module to test.
# We will reload it in specific tests to check its import-time setup.
from src.shared import honeypot_logger

class TestJsonFormatter(unittest.TestCase):
    def test_format_log_record(self):
        """Test that JsonFormatter correctly formats a LogRecord."""
        formatter = honeypot_logger.JsonFormatter()
        
        # Create a dummy LogRecord
        record_data = {
            'name': 'test_logger', 'levelno': logging.INFO, 'levelname': 'INFO',
            'pathname': 'test_path.py', 'filename': 'test_path.py', 'module': 'test_path',
            'lineno': 123, 'funcName': 'test_func',
            'created': 1678886400.0, # Fixed epoch seconds for reproducible timestamp
            'message': 'Original message before args' # This is record.msg
        }
        record = logging.LogRecord(
            name=record_data['name'], level=record_data['levelno'],
            pathname=record_data['pathname'], lineno=record_data['lineno'],
            msg="Test log message with args: %s", # Original message string
            args=("arg1",), 
            exc_info=None, func=record_data['funcName']
        )
        record.created = record_data['created'] # Override for consistent timestamp
        record.levelname = record_data['levelname'] # Ensure levelname is set
        
        # Simulate 'extra' details that would be passed to logger.info(..., extra=...)
        record.details = {"ip": "1.2.3.4", "custom_field": "value"}

        formatted_json_str = formatter.format(record)
        formatted_data = json.loads(formatted_json_str)

        expected_timestamp = (
            datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc)
            .isoformat()
            .replace('+00:00', 'Z')
        )
        
        self.assertEqual(formatted_data['timestamp'], expected_timestamp)
        self.assertEqual(formatted_data['level'], 'INFO')
        # record.getMessage() is called by formatter.format() to get the final message
        self.assertEqual(formatted_data['message'], "Test log message with args: arg1") 
        self.assertEqual(formatted_data['ip'], "1.2.3.4")
        self.assertEqual(formatted_data['custom_field'], "value")

class TestLogHoneypotHitFunction(unittest.TestCase):

    @patch.object(honeypot_logger.honeypot_logger, 'info') 
    def test_log_honeypot_hit_success(self, mock_logger_info):
        """Test successful logging by log_honeypot_hit."""
        details = {"ip": "192.168.1.100", "path": "/decoy"}
        honeypot_logger.log_honeypot_hit(details)
        
        mock_logger_info.assert_called_once_with(
            "Honeypot triggered", # The message string
            extra={'details': details} # The 'extra' dictionary
        )

    @patch.object(honeypot_logger.honeypot_logger, 'info', side_effect=Exception("Logger failed"))
    @patch('builtins.print') 
    def test_log_honeypot_hit_logger_exception(self, mock_print, mock_logger_info):
        """Test fallback print when logger.info raises an exception."""
        details = {"ip": "10.0.0.5", "error_trigger": True}
        honeypot_logger.log_honeypot_hit(details)
        
        mock_logger_info.assert_called_once() 
        mock_print.assert_called_once()
        args, _ = mock_print.call_args
        self.assertIn("ERROR in log_honeypot_hit: Logger failed", args[0])
        self.assertIn("'ip': '10.0.0.5'", args[0]) # Check details are in fallback print


class TestHoneypotLoggerSetup(unittest.TestCase):
    
    def setUp(self):
        # Store original handlers to restore them if they exist
        self.original_handlers = list(honeypot_logger.honeypot_logger.handlers)
        honeypot_logger.honeypot_logger.handlers = [] # Clear handlers for test
        # Store original HONEYPOT_LOG_FILE and patch it
        self.original_log_file = honeypot_logger.HONEYPOT_LOG_FILE
        self.test_log_file = "test_temp_honeypot_hits.log"
        honeypot_logger.HONEYPOT_LOG_FILE = self.test_log_file


    def tearDown(self):
        # Clean up handlers added during the test
        for handler in list(honeypot_logger.honeypot_logger.handlers):
            honeypot_logger.honeypot_logger.removeHandler(handler)
            if hasattr(handler, 'close'): # Close file handlers
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
    def test_logger_setup_on_import_or_reload(self, mock_makedirs, mock_getLogger, mock_FileHandler):
        """Test the logger setup logic that runs on module import/reload."""
        
        mock_logger_instance = MagicMock(spec=logging.Logger)
        mock_logger_instance.hasHandlers.return_value = False 
        mock_getLogger.return_value = mock_logger_instance
        
        mock_file_handler_instance = MagicMock(spec=logging.FileHandler)
        mock_FileHandler.return_value = mock_file_handler_instance

        # Reload the module to trigger setup logic
        importlib.reload(honeypot_logger)

        mock_makedirs.assert_called_once_with(os.path.dirname(self.test_log_file), exist_ok=True)
        mock_getLogger.assert_called_with('honeypot_logger')
        self.assertEqual(mock_logger_instance.level, logging.INFO)
        self.assertFalse(mock_logger_instance.propagate)
        mock_FileHandler.assert_called_once_with(self.test_log_file)
        mock_file_handler_instance.setFormatter.assert_called_once()
        formatter_arg = mock_file_handler_instance.setFormatter.call_args[0][0]
        self.assertIsInstance(formatter_arg, honeypot_logger.JsonFormatter)
        mock_logger_instance.addHandler.assert_called_once_with(mock_file_handler_instance)

    @patch("logging.FileHandler", side_effect=IOError("Cannot open file"))
    @patch("logging.getLogger")
    @patch("os.makedirs")
    @patch('builtins.print') 
    def test_logger_setup_filehandler_exception(self, mock_print, mock_makedirs, mock_getLogger, mock_FileHandler):
        mock_logger_instance = MagicMock(spec=logging.Logger)
        mock_logger_instance.hasHandlers.return_value = False 
        mock_getLogger.return_value = mock_logger_instance

        importlib.reload(honeypot_logger)

        mock_makedirs.assert_called_once_with(os.path.dirname(self.test_log_file), exist_ok=True)
        mock_FileHandler.assert_called_once_with(self.test_log_file)
        mock_print.assert_any_call(f"ERROR setting up honeypot file logger: Cannot open file")
        mock_logger_instance.addHandler.assert_not_called()

    @patch("logging.getLogger")
    def test_logger_setup_skips_if_handlers_exist(self, mock_getLogger):
        mock_logger_instance = MagicMock(spec=logging.Logger)
        mock_logger_instance.hasHandlers.return_value = True 
        mock_getLogger.return_value = mock_logger_instance

        with patch("logging.FileHandler") as mock_FileHandler_skipped: 
            importlib.reload(honeypot_logger)
            mock_FileHandler_skipped.assert_not_called()
            mock_logger_instance.addHandler.assert_not_called()


if __name__ == '__main__':
    unittest.main()
