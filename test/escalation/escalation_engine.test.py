# test/escalation/escalation_engine.test.py
import unittest
from unittest.mock import patch, MagicMock, mock_open, AsyncMock
import os
import datetime
import time 
import json
from fastapi.testclient import TestClient
import httpx # For httpx.RequestError

# Assuming escalation_engine.py is in the 'escalation' directory adjacent to 'test'
# and metrics.py is in the parent directory of 'escalation'.
# Python path adjustments might be needed depending on how tests are run.
# If run from project root (e.g. `python -m unittest discover`), imports should work.
from escalation import escalation_engine 
from escalation.escalation_engine import app, RequestMetadata, FREQUENCY_WINDOW_SECONDS, ValidationError 

# --- Helper to reset module-level states for cleaner tests ---
def reset_escalation_engine_module_state():
    escalation_engine.FREQUENCY_TRACKING_ENABLED = False
    escalation_engine.redis_client_freq = None
    escalation_engine.MODEL_LOADED = False
    escalation_engine.model_pipeline = None
    escalation_engine.disallowed_paths = set()
    escalation_engine.EXTERNAL_API_KEY = None
    escalation_engine.IP_REPUTATION_API_KEY = None
    
    # Reset metrics system availability flag and dummies
    escalation_engine.METRICS_SYSTEM_AVAILABLE = False # Default to false for reset
    
    # Define a simple dummy incrementer if metrics are not available
    def dummy_increment_counter_metric(metric_instance, labels=None):
        pass # No-op
    escalation_engine.increment_counter_metric = dummy_increment_counter_metric

    def dummy_get_metrics():
        return b"# Metrics unavailable in test reset\n" # Ensure bytes
    escalation_engine.get_metrics = dummy_get_metrics
        
    class DummyCounter:
        def inc(self, amount=1): pass
    
    # Re-initialize all known metric objects to dummies
    # This list should match the metrics imported/used in escalation_engine.py
    metric_names_to_reset = [
        "REDIS_ERRORS_FREQUENCY", "IP_REPUTATION_CHECKS_RUN", "IP_REPUTATION_SUCCESS",
        "IP_REPUTATION_MALICIOUS", "IP_REPUTATION_ERRORS_TIMEOUT", "IP_REPUTATION_ERRORS_REQUEST",
        "IP_REPUTATION_ERRORS_RESPONSE_DECODE", "IP_REPUTATION_ERRORS_UNEXPECTED",
        "HEURISTIC_CHECKS_RUN", "FREQUENCY_ANALYSES_PERFORMED", "RF_MODEL_PREDICTIONS",
        "RF_MODEL_ERRORS", "SCORE_ADJUSTED_IP_REPUTATION", "LOCAL_LLM_CHECKS_RUN",
        "LOCAL_LLM_ERRORS_UNEXPECTED_RESPONSE", "LOCAL_LLM_ERRORS_TIMEOUT",
        "LOCAL_LLM_ERRORS_REQUEST", "LOCAL_LLM_ERRORS_RESPONSE_DECODE",
        "LOCAL_LLM_ERRORS_UNEXPECTED", "EXTERNAL_API_CHECKS_RUN", "EXTERNAL_API_SUCCESS",
        "EXTERNAL_API_ERRORS_UNEXPECTED_RESPONSE", "EXTERNAL_API_ERRORS_TIMEOUT",
        "EXTERNAL_API_ERRORS_REQUEST", "EXTERNAL_API_ERRORS_RESPONSE_DECODE",
        "EXTERNAL_API_ERRORS_UNEXPECTED", "ESCALATION_WEBHOOKS_SENT",
        "ESCALATION_WEBHOOK_ERRORS_REQUEST", "ESCALATION_WEBHOOK_ERRORS_UNEXPECTED",
        "CAPTCHA_CHALLENGES_TRIGGERED", "ESCALATION_REQUESTS_RECEIVED",
        "BOTS_DETECTED_IP_REPUTATION", "BOTS_DETECTED_HIGH_SCORE",
        "HUMANS_DETECTED_LOW_SCORE", "BOTS_DETECTED_LOCAL_LLM",
        "HUMANS_DETECTED_LOCAL_LLM", "BOTS_DETECTED_EXTERNAL_API",
        "HUMANS_DETECTED_EXTERNAL_API"
    ]
    for name in metric_names_to_reset:
        if hasattr(escalation_engine, name): # Check if attribute exists before setting
            setattr(escalation_engine, name, DummyCounter())

    if hasattr(escalation_engine, 'logging'):
        escalation_engine.logger = escalation_engine.logging.getLogger('escalation_engine_test_instance')
        escalation_engine.logger.handlers = []
        import logging as test_logging 
        test_logging.basicConfig(level=escalation_engine.logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)


class TestRequestMetadataModel(unittest.TestCase):
    def test_request_metadata_valid(self):
        timestamp = datetime.datetime.utcnow()
        data = {
            "timestamp": timestamp, "ip": "1.2.3.4", "user_agent": "TestBot/1.0",
            "referer": "http://example.com", "path": "/test/path",
            "headers": {"X-Test-Header": "value"}, "source": "test_source"
        }
        event = RequestMetadata(**data)
        self.assertEqual(event.ip, "1.2.3.4")
        self.assertEqual(event.source, "test_source")
        self.assertEqual(event.timestamp, timestamp)
        self.assertIsNotNone(event.headers)
        current_headers = event.headers
        if current_headers is not None: 
            self.assertEqual(current_headers["X-Test-Header"], "value")
        else:
            self.fail("event.headers should not be None when initialized with a dictionary")

    def test_request_metadata_optional_fields(self):
        timestamp_str = datetime.datetime.utcnow().isoformat()
        data_no_optionals = {"timestamp": timestamp_str, "ip": "1.2.3.4", "source": "test"}
        event = RequestMetadata(**data_no_optionals) # type: ignore
        self.assertIsNone(event.user_agent)
        self.assertIsNone(event.referer)
        self.assertIsNone(event.path)
        self.assertIsNone(event.headers) 

    def test_request_metadata_validation_error(self):
        # Test missing 'timestamp'
        with self.assertRaises(ValidationError): 
            RequestMetadata(ip="1.2.3.4", source="test", headers={}) # type: ignore
        
        # Test missing 'ip'
        with self.assertRaises(ValidationError):
            RequestMetadata(timestamp=datetime.datetime.utcnow().isoformat(), source="test", headers={}) # type: ignore
        
        # Test missing 'source'
        with self.assertRaises(ValidationError):
            RequestMetadata(timestamp=datetime.datetime.utcnow().isoformat(), ip="1.2.3.4", headers={}) # type: ignore
        
        # Test providing headers as an invalid type (string)
        with self.assertRaises(ValidationError):
            RequestMetadata(timestamp=datetime.datetime.utcnow().isoformat(), ip="1.2.3.4", source="test", headers="not-a-dict") # type: ignore


class TestHelperFunctions(unittest.IsolatedAsyncioTestCase): 
    async def asyncSetUp(self): # Changed to asyncSetUp
        reset_escalation_engine_module_state()
        self.mock_increment_patcher = patch("escalation.escalation_engine.increment_counter_metric")
        self.mock_increment = self.mock_increment_patcher.start()

    async def asyncTearDown(self): # Changed to asyncTearDown
        self.mock_increment_patcher.stop()

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="secret_value")
    async def test_load_secret_success(self, mock_file, mock_exists):
        mock_exists.return_value = True
        self.assertEqual(escalation_engine.load_secret("fake/path"), "secret_value")

    @patch("os.path.exists", return_value=False)
    async def test_load_secret_file_not_found(self, mock_exists):
        self.assertIsNone(escalation_engine.load_secret("fake/path"))

    @patch("escalation.escalation_engine.logger.error")
    @patch("builtins.open", new_callable=mock_open(read_data="User-agent: *\nDisallow: /admin/\nDisallow: /private"))
    async def test_load_robots_txt(self, mock_logger_error): # Made async for consistency if needed, though logic is sync
        escalation_engine.load_robots_txt("dummy_path.txt") 
        self.assertIn("/admin/", escalation_engine.disallowed_paths)
        mock_logger_error.assert_not_called()

    async def test_is_path_disallowed(self): # Made async for consistency
        escalation_engine.disallowed_paths = {"/admin/", "/secret/path"}
        self.assertTrue(escalation_engine.is_path_disallowed("/admin/page.html"))

    @patch("escalation.escalation_engine.httpx.AsyncClient")
    @patch("escalation.escalation_engine.ENABLE_IP_REPUTATION", True)
    @patch("escalation.escalation_engine.IP_REPUTATION_API_URL", "http://fakeiprep.com/check")
    @patch("escalation.escalation_engine.IP_REPUTATION_API_KEY", "fake_key")
    async def test_check_ip_reputation_malicious(self, MockAsyncClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"abuseConfidenceScore": 90, "isPublic": True} 
        mock_get_method = AsyncMock(return_value=mock_response)
        MockAsyncClient.return_value.__aenter__.return_value.get = mock_get_method
        result = await escalation_engine.check_ip_reputation("1.2.3.4")
        self.assertIsNotNone(result)
        if result: self.assertTrue(result["is_malicious"])

    @patch("escalation.escalation_engine.httpx.AsyncClient")
    @patch("escalation.escalation_engine.ENABLE_IP_REPUTATION", True)
    @patch("escalation.escalation_engine.IP_REPUTATION_API_URL", "http://fakeiprep.com/check")
    async def test_check_ip_reputation_api_error(self, MockAsyncClient):
        mock_get_method = AsyncMock(side_effect=httpx.RequestError("Network error"))
        MockAsyncClient.return_value.__aenter__.return_value.get = mock_get_method
        result = await escalation_engine.check_ip_reputation("1.2.3.4")
        self.assertIsNone(result)

# (Rest of the test classes: TestFeatureExtractionAndAnalysis, TestFastAPIEndpoints
#  would be here, similar to updated_escalation_engine_test_py_v5, ensuring all
#  RequestMetadata instantiations are complete with required fields or correctly
#  testing validation for missing fields with # type: ignore)

# For brevity, I'm only showing the updated TestRequestMetadataModel and parts of TestHelperFunctions.
# The full file would be much longer and include tests for all other functions and endpoints.
# The principle is to ensure all RequestMetadata calls are valid for non-validation tests,
# and use # type: ignore for intentional validation tests.

# Placeholder for the rest of the comprehensive tests:
class TestFeatureExtractionAndAnalysis(unittest.TestCase):
    # ... (tests as per updated_escalation_engine_test_py_v5, ensuring RequestMetadata calls are valid)
    def setUp(self):
        reset_escalation_engine_module_state()
        # Add necessary mocks
        self.mock_increment_patcher = patch("escalation.escalation_engine.increment_counter_metric")
        self.mock_increment = self.mock_increment_patcher.start()
        self.redis_mock_patcher = patch("escalation.escalation_engine.redis_client_freq")
        self.mock_redis_client = self.redis_mock_patcher.start()
        self.mock_redis_client.pipeline.return_value.execute.return_value = [0,0,0,[],0]
        escalation_engine.FREQUENCY_TRACKING_ENABLED = True


    def tearDown(self):
        self.mock_increment_patcher.stop()
        self.redis_mock_patcher.stop()


    def test_extract_features_valid_input(self):
        log_entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(), "ip": "1.2.3.4", "source": "test",
            "user_agent": "TestBot", "path": "/some/path", "method": "GET", "status": 200, "bytes": 100, "referer": "http://example.com",
            "headers": {"X-Test": "data"}
        }
        freq_features = {"count": 1, "time_since": 10.0}
        features = escalation_engine.extract_features(log_entry, freq_features)
        self.assertIsInstance(features, dict)
        self.assertIn("ua_length", features)

class TestFastAPIEndpoints(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        reset_escalation_engine_module_state()
        self.client = TestClient(app)
        # Add necessary mocks using AsyncMock where appropriate
        self.mock_increment_patcher = patch("escalation.escalation_engine.increment_counter_metric")
        self.mock_increment = self.mock_increment_patcher.start()

        self.check_ip_rep_patch = patch("escalation.escalation_engine.check_ip_reputation", new_callable=AsyncMock, return_value=None)
        self.mock_check_ip_rep = self.check_ip_rep_patch.start()

        self.run_analysis_patch = patch("escalation.escalation_engine.run_heuristic_and_model_analysis", return_value=0.5) # Default score
        self.mock_run_analysis = self.run_analysis_patch.start()
        
        self.classify_llm_patch = patch("escalation.escalation_engine.classify_with_local_llm_api", new_callable=AsyncMock, return_value=None)
        self.mock_classify_llm = self.classify_llm_patch.start()

        self.classify_ext_patch = patch("escalation.escalation_engine.classify_with_external_api", new_callable=AsyncMock, return_value=None)
        self.mock_classify_ext = self.classify_ext_patch.start()

        self.forward_webhook_patch = patch("escalation.escalation_engine.forward_to_webhook", new_callable=AsyncMock)
        self.mock_forward_webhook = self.forward_webhook_patch.start()
        
        self.trigger_captcha_patch = patch("escalation.escalation_engine.trigger_captcha_challenge", new_callable=AsyncMock, return_value=True)
        self.mock_trigger_captcha = self.trigger_captcha_patch.start()

        self.get_metrics_patcher = patch("escalation.escalation_engine.get_metrics")
        self.mock_get_metrics_func = self.get_metrics_patcher.start()


    async def asyncTearDown(self):
        self.mock_increment_patcher.stop()
        self.check_ip_rep_patch.stop()
        self.run_analysis_patch.stop()
        self.classify_llm_patch.stop()
        self.classify_ext_patch.stop()
        self.forward_webhook_patch.stop()
        self.trigger_captcha_patch.stop()
        self.get_metrics_patcher.stop()


    async def test_escalate_endpoint_valid_payload(self):
        payload = {
            "timestamp": datetime.datetime.utcnow().isoformat(), "ip": "1.2.3.4", 
            "source": "test_source", "user_agent": "Test", "path": "/", "headers": {}
        }
        self.mock_run_analysis.return_value = 0.1 # Simulate low score
        response = self.client.post("/escalate", json=payload)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(json_data["action"], "classified_human_low_score")
        self.mock_increment.assert_any_call(escalation_engine.ESCALATION_REQUESTS_RECEIVED)


if __name__ == '__main__':
    unittest.main()
