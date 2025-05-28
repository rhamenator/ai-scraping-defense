# test\ai_service\ai_webhook.test.py

import unittest
from unittest.mock import patch, mock_open
from datetime import datetime
from ai_service import ai_webhook
import os


class TestWebhookEvent(unittest.TestCase):

    def test_webhook_event_initialization_and_dict(self):
        event = ai_webhook.WebhookEvent(
            event_type="suspicious_activity_detected",
            reason="Threshold exceeded",
            timestamp_utc=datetime.utcnow().isoformat(),
            details={"ip": "1.2.3.4", "ua": "test-agent", "threat": "aggressive"}
        )
        self.assertEqual(event.event_type, "suspicious_activity_detected")
        self.assertIn("ip", event.details)
        self.assertIn("ua", event.details)
        self.assertIn("threat", event.details)


class TestLoadSecret(unittest.TestCase):

    @patch.dict(os.environ, {"AI_SHARED_SECRET": "topsecret"})
    def test_load_secret_from_env(self):
        secret = ai_webhook.load_secret(None) # Pass None as file_path
        self.assertEqual(secret, "topsecret")

    @patch.dict(os.environ, {}, clear=True)
    @patch("builtins.open", new_callable=mock_open, read_data="fallbacksecret\n")
    def test_load_secret_from_file(self, mock_file):
        secret = ai_webhook.load_secret("/path/to/secret") # Pass a file_path
        self.assertEqual(secret, "fallbacksecret")
        mock_file.assert_called_once()


class TestLogging(unittest.TestCase):

    @patch("builtins.print")
    def test_log_event_prints_expected_fields(self, mock_print):
        ai_webhook.log_event(
            log_file="test_log.log",
            event_type="rate_limit_triggered",
            data={"ip": "5.6.7.8", "ua": "PythonBot"}
        )
        output = " ".join(str(arg) for call in mock_print.call_args_list for arg in call[0])
        self.assertIn("rate_limit_triggered", output)
        self.assertIn("5.6.7.8", output)

    @patch("builtins.print")
    def test_log_error_prints_exception_string(self, mock_print):
        ai_webhook.log_error("Rate limit exception raised")
        output = " ".join(str(arg) for call in mock_print.call_args_list for arg in call[0])
        self.assertIn("Rate limit exception", output)


class TestBlocklist(unittest.TestCase):

    @patch("builtins.open", new_callable=mock_open)
    def test_add_ip_to_blocklist_appends(self, mock_file):
        ai_webhook.add_ip_to_blocklist(
            ip_address="6.6.6.6",
            reason="Repeated probing behavior",
            event_details={"ip": "6.6.6.6", "user_agent": "BadBot"}
        )
        mock_file.assert_called_once_with("ip_blocklist.txt", "a")
        mock_file().write.assert_called_once()
        written = mock_file().write.call_args[0][0]
        self.assertIn("6.6.6.6", written)
        self.assertIn("Repeated probing behavior", written)


if __name__ == '__main__':
    unittest.main()
