# test/ai_service/ai_webhook.test.py
import unittest
from unittest.mock import patch, mock_open, MagicMock, AsyncMock
from fastapi.testclient import TestClient
import os
import json
import datetime
import smtplib # For type checking exceptions
import logging 
import asyncio  

from ai_service import ai_webhook
from ai_service.ai_webhook import app, WebhookEvent 

# --- Helper to reset module-level states if needed ---
def reset_ai_webhook_module_state():
    """Resets some global states in ai_webhook for cleaner tests."""
    ai_webhook.BLOCKLISTING_ENABLED = False
    ai_webhook.redis_client_blocklist = None
    ai_webhook.ALERT_SMTP_PASSWORD = None
    ai_webhook.COMMUNITY_BLOCKLIST_API_KEY = None
    
    ai_webhook.METRICS_SYSTEM_AVAILABLE = False
    def dummy_increment_counter_metric(metric_instance, labels=None): pass
    ai_webhook.increment_counter_metric = dummy_increment_counter_metric
    class DummyCounter:
        def inc(self, amount=1): pass
    ai_webhook.COMMUNITY_REPORTS_ATTEMPTED = DummyCounter()
    ai_webhook.COMMUNITY_REPORTS_SUCCESS = DummyCounter()
    ai_webhook.COMMUNITY_REPORTS_ERRORS_TIMEOUT = DummyCounter()
    ai_webhook.COMMUNITY_REPORTS_ERRORS_REQUEST = DummyCounter()
    ai_webhook.COMMUNITY_REPORTS_ERRORS_STATUS = DummyCounter()
    ai_webhook.COMMUNITY_REPORTS_ERRORS_RESPONSE_DECODE = DummyCounter()
    ai_webhook.COMMUNITY_REPORTS_ERRORS_UNEXPECTED = DummyCounter()

    if hasattr(ai_webhook, 'logging'):
        ai_webhook.logger = ai_webhook.logging.getLogger('ai_webhook_test_instance_reset') 
        ai_webhook.logger.handlers = [] 
        # BasicConfig might conflict if already configured by test runner, use specific handlers or ensure force=True if needed.
        # For test isolation, it's often better that the module under test does its own logging setup
        # and tests can capture that, rather than tests reconfiguring the module's logger.
        # ai_webhook.logging.basicConfig(level=ai_webhook.logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)


class TestWebhookEventModel(unittest.TestCase):
    def test_webhook_event_valid(self):
        timestamp = datetime.datetime.utcnow().isoformat()
        data = {
            "event_type": "suspicious_activity",
            "reason": "High score",
            "timestamp_utc": timestamp,
            "details": {"ip": "1.2.3.4", "ua": "TestBot"}
        }
        event = WebhookEvent(**data)
        self.assertEqual(event.event_type, "suspicious_activity")
        self.assertEqual(event.details["ip"], "1.2.3.4")

    def test_webhook_event_missing_required_field(self):
        timestamp = datetime.datetime.utcnow().isoformat()
        data = {
            "reason": "High score", 
            "timestamp_utc": timestamp,
            "details": {"ip": "1.2.3.4"}
        }
        with self.assertRaises(ai_webhook.ValidationError): 
            WebhookEvent(**data)

class TestLoadSecret(unittest.TestCase):
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="file_secret_value")
    def test_load_secret_from_file_success(self, mock_file_open, mock_path_exists):
        mock_path_exists.return_value = True
        secret = ai_webhook.load_secret("/fake/path/to/secret.txt")
        self.assertEqual(secret, "file_secret_value")

    @patch("os.path.exists", return_value=False)
    def test_load_secret_file_not_exists(self, mock_path_exists):
        secret = ai_webhook.load_secret("/fake/path/nonexistent.txt")
        self.assertIsNone(secret)

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", side_effect=IOError("File read error"))
    @patch("ai_service.ai_webhook.logger.error")
    def test_load_secret_file_read_error(self, mock_logger_error, mock_file_open, mock_path_exists):
        secret = ai_webhook.load_secret("/fake/path/error.txt")
        self.assertIsNone(secret)
        mock_logger_error.assert_called_once()

    def test_load_secret_none_path(self):
        secret = ai_webhook.load_secret(None)
        self.assertIsNone(secret)

class TestLoggingFunctions(unittest.TestCase):
    @patch("builtins.open", new_callable=mock_open)
    @patch("ai_service.ai_webhook.logger.error") 
    def test_log_error_file_write(self, mock_std_logger_error, mock_file_open):
        ai_webhook.log_error("Test error message", exception=ValueError("Test Exception"))
        mock_std_logger_error.assert_called_once()
        mock_file_open.assert_called_with(ai_webhook.ERROR_LOG_FILE, "a", encoding="utf-8")
        mock_file_open().write.assert_called()

    @patch("builtins.open", new_callable=mock_open)
    @patch("ai_service.ai_webhook.json.dumps") 
    def test_log_event_file_write(self, mock_json_dumps, mock_file_open):
        test_data = {"ip": "1.2.3.4", "action": "blocked"}
        ai_webhook.log_event(ai_webhook.BLOCK_LOG_FILE, "BLOCK_EVENT", test_data)
        mock_json_dumps.assert_any_call(test_data, default=str)
        final_dump_args = mock_json_dumps.call_args_list[-1][0][0]
        self.assertEqual(final_dump_args["event_type"], "BLOCK_EVENT")
        mock_file_open.assert_called_with(ai_webhook.BLOCK_LOG_FILE, "a", encoding="utf-8")
        mock_file_open().write.assert_called()

class TestRedisInteractions(unittest.TestCase):
    def setUp(self):
        reset_ai_webhook_module_state() # Call reset helper
        self.redis_mock_patcher = patch("ai_service.ai_webhook.redis_client_blocklist")
        self.mock_redis_client = self.redis_mock_patcher.start()
        self.logger_patcher = patch("ai_service.ai_webhook.logger")
        self.mock_logger = self.logger_patcher.start()
        self.log_event_patcher = patch("ai_service.ai_webhook.log_event")
        self.mock_log_event = self.log_event_patcher.start()
        self.blocklisting_enabled_patcher = patch("ai_service.ai_webhook.BLOCKLISTING_ENABLED", True)
        self.mock_blocklisting_enabled = self.blocklisting_enabled_patcher.start()
        self.log_error_patcher = patch("ai_service.ai_webhook.log_error")
        self.mock_log_error = self.log_error_patcher.start()

    def tearDown(self):
        self.redis_mock_patcher.stop()
        self.logger_patcher.stop()
        self.log_event_patcher.stop()
        self.blocklisting_enabled_patcher.stop()
        self.log_error_patcher.stop()

    def test_add_ip_to_blocklist_success(self):
        self.mock_redis_client.setex.return_value = True
        result = ai_webhook.add_ip_to_blocklist("1.2.3.4", "Test reason", {"user_agent": "TestUA"})
        self.assertTrue(result)
        self.mock_redis_client.setex.assert_called_once()
        args, _ = self.mock_redis_client.setex.call_args
        self.assertEqual(args[0], f"{ai_webhook.BLOCKLIST_KEY_PREFIX}1.2.3.4")
        self.mock_log_event.assert_called_once()

    def test_add_ip_to_blocklist_redis_disabled(self):
        with patch("ai_service.ai_webhook.BLOCKLISTING_ENABLED", False):
            result = ai_webhook.add_ip_to_blocklist("1.2.3.4", "Test reason")
            self.assertFalse(result)
            self.mock_redis_client.setex.assert_not_called()

    def test_add_ip_to_blocklist_unknown_ip(self):
        result = ai_webhook.add_ip_to_blocklist("unknown", "Test reason")
        self.assertFalse(result)
        self.mock_redis_client.setex.assert_not_called()
        self.mock_logger.warning.assert_called_once()

    def test_add_ip_to_blocklist_redis_error(self):
        self.mock_redis_client.setex.side_effect = ai_webhook.RedisError("Connection failed")
        result = ai_webhook.add_ip_to_blocklist("1.2.3.4", "Test reason")
        self.assertFalse(result)
        self.mock_redis_client.setex.assert_called_once()
        self.mock_log_error.assert_called_once()

# Use IsolatedAsyncioTestCase for tests involving asyncio.run or async def test methods
class TestAlertingFunctions(unittest.IsolatedAsyncioTestCase):
    
    async def asyncSetUp(self): # Changed to asyncSetUp
        reset_ai_webhook_module_state() # Call reset helper
        self.event_data = WebhookEvent(
            event_type="test_event",
            reason="Test Reason (Severity)",
            timestamp_utc=datetime.datetime.utcnow(),
            details={"ip": "1.2.3.4", "user_agent": "TestAgent"}
        )
        self.increment_counter_metric_patcher = patch("ai_service.ai_webhook.increment_counter_metric")
        self.mock_increment_counter_metric = self.increment_counter_metric_patcher.start()

    async def asyncTearDown(self): # Changed to asyncTearDown
        self.increment_counter_metric_patcher.stop()

    @patch("ai_service.ai_webhook.httpx.AsyncClient")
    @patch("ai_service.ai_webhook.ALERT_GENERIC_WEBHOOK_URL", "http://fakeurl.com/webhook")
    async def test_send_generic_webhook_alert_success(self, MockAsyncClient): # Now async def
        mock_post = AsyncMock()
        MockAsyncClient.return_value.__aenter__.return_value.post = mock_post
        await ai_webhook.send_generic_webhook_alert(self.event_data) # Use await
        mock_post.assert_called_once()

    @patch("ai_service.ai_webhook.requests.post")
    @patch("ai_service.ai_webhook.asyncio.to_thread", new_callable=AsyncMock) 
    @patch("ai_service.ai_webhook.ALERT_SLACK_WEBHOOK_URL", "http://fakeslack.com/webhook")
    async def test_send_slack_alert_success(self, mock_to_thread, mock_requests_post): # Now async def
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_requests_post.return_value = mock_response
        async def fake_to_thread_call(func, *args, **kwargs): return func(*args, **kwargs)
        mock_to_thread.side_effect = fake_to_thread_call
        await ai_webhook.send_slack_alert(self.event_data) # Use await
        mock_requests_post.assert_called_once()

    @patch("smtplib.SMTP_SSL")
    @patch("smtplib.SMTP")
    @patch("ai_service.ai_webhook.ALERT_METHOD", "smtp")
    @patch("ai_service.ai_webhook.ALERT_EMAIL_TO", "receiver@example.com")
    @patch("ai_service.ai_webhook.ALERT_SMTP_HOST", "smtp.example.com")
    @patch("ai_service.ai_webhook.ALERT_EMAIL_FROM", "sender@example.com")
    @patch("ai_service.ai_webhook.ALERT_SMTP_USER", "user")
    @patch("ai_service.ai_webhook.ALERT_SMTP_PASSWORD", "pass")
    @patch("ai_service.ai_webhook.ALERT_SMTP_USE_TLS", True)
    @patch("ai_service.ai_webhook.ALERT_SMTP_PORT", 587) 
    async def test_send_smtp_alert_success_tls_standard_port(self, MockSMTP, MockSMTP_SSL): # Now async def
        mock_smtp_instance = MagicMock()
        MockSMTP.return_value = mock_smtp_instance
        await ai_webhook.send_smtp_alert(self.event_data) # Use await
        MockSMTP.assert_called_with("smtp.example.com", 587, timeout=15)
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_with("user", "pass")
        mock_smtp_instance.sendmail.assert_called_once()
        mock_smtp_instance.quit.assert_called_once()
        
    @patch("ai_service.ai_webhook.send_generic_webhook_alert", new_callable=AsyncMock)
    @patch("ai_service.ai_webhook.send_slack_alert", new_callable=AsyncMock)
    @patch("ai_service.ai_webhook.send_smtp_alert", new_callable=AsyncMock)
    async def test_send_alert_dispatches_correctly(self, mock_smtp, mock_slack, mock_generic_webhook): # Now async def
        with patch("ai_service.ai_webhook.ALERT_METHOD", "webhook"):
            await ai_webhook.send_alert(self.event_data) # Use await
            mock_generic_webhook.assert_called_once_with(self.event_data)
        mock_generic_webhook.reset_mock()
        # ... (similar changes for slack and smtp cases)
        with patch("ai_service.ai_webhook.ALERT_METHOD", "slack"):
            await ai_webhook.send_alert(self.event_data)
            mock_slack.assert_called_once_with(self.event_data)
        mock_slack.reset_mock()
        with patch("ai_service.ai_webhook.ALERT_METHOD", "smtp"):
            await ai_webhook.send_alert(self.event_data)
            mock_smtp.assert_called_once_with(self.event_data)
        mock_smtp.reset_mock()


    @patch("ai_service.ai_webhook.send_generic_webhook_alert", new_callable=AsyncMock)
    async def test_send_alert_severity_filter(self, mock_generic_webhook): # Now async def
        low_sev_event = WebhookEvent(event_type="low_sev", reason="Low Score (0.1)", timestamp_utc=datetime.datetime.utcnow(), details={"ip": "1.2.3.4"})
        with patch("ai_service.ai_webhook.ALERT_METHOD", "webhook"), \
             patch("ai_service.ai_webhook.ALERT_MIN_REASON_SEVERITY", "High Heuristic"):
            await ai_webhook.send_alert(low_sev_event) # Use await
            mock_generic_webhook.assert_not_called()

class TestCommunityReporting(unittest.IsolatedAsyncioTestCase): 
    async def asyncSetUp(self): # Changed to asyncSetUp
        reset_ai_webhook_module_state() # Call reset helper
        self.details = {"ip": "1.2.3.4", "user_agent": "TestAgent", "path": "/test"}
        self.increment_counter_metric_patcher = patch("ai_service.ai_webhook.increment_counter_metric")
        self.mock_increment_counter_metric = self.increment_counter_metric_patcher.start()

    async def asyncTearDown(self): # Changed to asyncTearDown
        self.increment_counter_metric_patcher.stop()

    @patch("ai_service.ai_webhook.httpx.AsyncClient")
    @patch("ai_service.ai_webhook.ENABLE_COMMUNITY_REPORTING", True)
    @patch("ai_service.ai_webhook.COMMUNITY_BLOCKLIST_REPORT_URL", "http://fakeblocklist.com/report")
    @patch("ai_service.ai_webhook.COMMUNITY_BLOCKLIST_API_KEY", "test_api_key")
    async def test_report_ip_to_community_success(self, MockAsyncClient): 
        mock_post = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success"}
        mock_post.return_value = mock_response
        MockAsyncClient.return_value.__aenter__.return_value.post = mock_post

        result = await ai_webhook.report_ip_to_community("1.2.3.4", "Scraping Activity", self.details)
        
        self.assertTrue(result)
        mock_post.assert_called_once()
        self.mock_increment_counter_metric.assert_any_call(ai_webhook.COMMUNITY_REPORTS_ATTEMPTED)
        self.mock_increment_counter_metric.assert_any_call(ai_webhook.COMMUNITY_REPORTS_SUCCESS)

    @patch("ai_service.ai_webhook.ENABLE_COMMUNITY_REPORTING", False)
    async def test_report_ip_to_community_disabled(self): 
        result = await ai_webhook.report_ip_to_community("1.2.3.4", "Scraping", self.details)
        self.assertFalse(result)
        self.mock_increment_counter_metric.assert_not_called()

class TestFastAPIEndpoints(unittest.TestCase): # Stays as TestCase, TestClient is synchronous
    def setUp(self):
        reset_ai_webhook_module_state() # Call reset helper
        self.client = TestClient(app)
        self.add_ip_patcher = patch("ai_service.ai_webhook.add_ip_to_blocklist", return_value=True)
        self.mock_add_ip = self.add_ip_patcher.start()
        self.report_community_patcher = patch("ai_service.ai_webhook.report_ip_to_community", new_callable=AsyncMock, return_value=True)
        self.mock_report_community = self.report_community_patcher.start()
        self.send_alert_patcher = patch("ai_service.ai_webhook.send_alert", new_callable=AsyncMock)
        self.mock_send_alert = self.send_alert_patcher.start()

    def tearDown(self):
        self.add_ip_patcher.stop()
        self.report_community_patcher.stop()
        self.send_alert_patcher.stop()

    def test_health_check_redis_ok(self):
        with patch("ai_service.ai_webhook.redis_client_blocklist") as mock_redis:
            mock_redis.ping.return_value = True
            response = self.client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok", "redis_blocklist_connected": True})

    def test_receive_webhook_success_auto_block(self):
        event_payload = {"event_type": "suspicious_activity", "reason": "High Combined Score (0.9)", "timestamp_utc": datetime.datetime.utcnow().isoformat(), "details": {"ip": "1.2.3.5", "user_agent": "NastyBot"}}
        response = self.client.post("/analyze", json=event_payload)
        self.assertEqual(response.status_code, 202)
        json_response = response.json()
        self.assertEqual(json_response["status"], "processed")
        self.mock_add_ip.assert_called_once_with("1.2.3.5", "High Combined Score (0.9)", event_payload["details"])
        self.mock_report_community.assert_called_once_with("1.2.3.5", "High Combined Score (0.9)", event_payload["details"])
        self.mock_send_alert.assert_called_once()

    def test_receive_webhook_invalid_payload(self):
        invalid_payload = {"reason": "Missing event_type", "details": {"ip": "1.2.3.4"}}
        response = self.client.post("/analyze", json=invalid_payload)
        self.assertEqual(response.status_code, 422)

if __name__ == '__main__':
    unittest.main()
# Note: The above test suite assumes that the ai_service module and its ai_webhook submodule
# are structured correctly and that the necessary imports and configurations are in place.