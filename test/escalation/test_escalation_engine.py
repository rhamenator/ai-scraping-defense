# test/escalation/escalation_engine.test.py
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import httpx
import datetime
import json
from fastapi.testclient import TestClient
import httpx
import sys
import os

# Add the project root to the path to help static analysis tools find the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.escalation import escalation_engine
# Correctly import only the existing classes from the module
from src.escalation.escalation_engine import app, RequestMetadata, ValidationError

class TestEscalationEngineComprehensive(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """Set up test client and patch external dependencies."""
        self.client = TestClient(app)
        self.env = patch.dict(os.environ, {"ESCALATION_API_KEY": "testkey"})
        self.env.start()
        sys.modules['escalation.escalation_engine'] = escalation_engine
        # Patch all key functions and module-level objects to isolate the endpoint logic
        self.patchers = {
            'load_robots_txt': patch('escalation.escalation_engine.load_robots_txt'),
            'get_redis_connection': patch('escalation.escalation_engine.get_redis_connection'),
            # Correctly patch the module-level variable, not the function that creates it
            'model_adapter': patch('escalation.escalation_engine.model_adapter', MagicMock()),
            'check_ip_reputation': patch('escalation.escalation_engine.check_ip_reputation', new_callable=AsyncMock),
            'get_frequency_features': patch('escalation.escalation_engine.get_realtime_frequency_features'),
            'classify_with_local_llm_api': patch('escalation.escalation_engine.classify_with_local_llm_api', new_callable=AsyncMock),
            'classify_with_external_api': patch('escalation.escalation_engine.classify_with_external_api', new_callable=AsyncMock),
            'forward_to_webhook': patch('escalation.escalation_engine.forward_to_webhook', new_callable=AsyncMock),
            'trigger_captcha_challenge': patch('escalation.escalation_engine.trigger_captcha_challenge', new_callable=AsyncMock)
        }
        self.mocks = {name: patcher.start() for name, patcher in self.patchers.items()}

        # Default mock behaviors
        self.mocks['get_redis_connection'].return_value = MagicMock()
        self.mocks['check_ip_reputation'].return_value = None
        self.mocks['get_frequency_features'].return_value = {'count': 1, 'time_since': 100}
        self.mocks['classify_with_local_llm_api'].return_value = None
        self.mocks['classify_with_external_api'].return_value = None
        self.mocks['trigger_captcha_challenge'].return_value = True # Assume captcha is "passed" if triggered

        # Ensure fingerprint tracking uses a mock redis client
        self.mocks['redis_fingerprints'] = MagicMock()
        escalation_engine.redis_client_fingerprints = self.mocks['redis_fingerprints']
        escalation_engine.FINGERPRINT_TRACKING_ENABLED = True
        self.mocks['redis_fingerprints'].scard.return_value = 1
        self.mocks['redis_fingerprints'].sadd.return_value = 1
        self.mocks['redis_fingerprints'].expire.return_value = True

    def tearDown(self):
        """Stop all patches."""
        for patcher in self.patchers.values():
            patcher.stop()
        self.env.stop()

    def test_request_metadata_validation(self):
        """Test RequestMetadata Pydantic model validation."""
        # Correctly added 'headers' to satisfy the model's type hints
        valid_data = {"timestamp": "2023-01-01T12:00:00Z", "ip": "1.1.1.1", "source": "test", "headers": None, "method": "GET"}
        self.assertTrue(RequestMetadata(**valid_data))
        with self.assertRaises(ValidationError):
            # This line is intentionally incorrect to test validation.
            # We add a 'type: ignore' comment to suppress the static analysis error.
            RequestMetadata(ip="1.1.1.1", source="test") # type: ignore

    def test_run_heuristic_and_model_analysis(self):
        """Test the combined heuristic and model scoring logic."""
        # Access the correctly patched model_adapter mock
        mock_model = self.mocks['model_adapter']
        mock_model.predict.return_value = [[0.2, 0.8]] # Simulate bot prediction
        
        # The function now takes a RequestMetadata object directly
        metadata = RequestMetadata(
            timestamp="2023-01-01T12:00:00Z",
            ip="1.2.3.4",
            source="test",
            user_agent="python-requests/2.25.1", # This is a known bad UA
            path="/wp-admin",
            method="GET"
        )
        
        # Ensure the model is "loaded" for this test
        with patch('escalation.escalation_engine.MODEL_LOADED', True):
            score = escalation_engine.run_heuristic_and_model_analysis(metadata)
        
        # Check that the score is a blend of heuristic and model
        self.assertGreater(score, 0.5) # Should be high due to bad UA and model
        mock_model.predict.assert_called_once()

    async def test_escalate_endpoint_human_low_score(self):
        """Test a request classified as human with a low score."""
        with patch('escalation.escalation_engine.run_heuristic_and_model_analysis', return_value=0.1):
            response = self.client.post("/escalate", json={"timestamp": "2023-01-01T12:00:00Z", "ip": "1.1.1.1", "source": "test", "method": "GET"}, headers={"X-API-Key": "testkey"})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['action'], 'classified_human_low_score')
        self.assertFalse(data['is_bot_decision'])
        self.mocks['forward_to_webhook'].assert_not_called()

    async def test_escalate_invalid_ip_address(self):
        """IP validation should reject malformed addresses."""
        payload = {"timestamp": "2023-01-01T12:00:00Z", "ip": "999.999.999.999", "source": "test", "method": "GET"}
        response = self.client.post("/escalate", json=payload, headers={"X-API-Key": "testkey"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid IP address", response.text)

    async def test_escalate_missing_or_bad_api_key(self):
        """Requests without the correct API key should be unauthorized."""
        payload = {"timestamp": "2023-01-01T12:00:00Z", "ip": "1.1.1.1", "source": "test", "method": "GET"}
        with patch("src.escalation.escalation_engine.ESCALATION_API_KEY", "testkey"):
            resp_missing = self.client.post("/escalate", json=payload)
            self.assertEqual(resp_missing.status_code, 401)
            resp_wrong = self.client.post("/escalate", json=payload, headers={"X-API-Key": "wrong"})
            self.assertEqual(resp_wrong.status_code, 401)

    async def test_check_ip_reputation_timeout_and_json_error(self):
        """Timeouts and JSON decode failures should return None."""
        metadata_url = "http://example.com"
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.side_effect = httpx.TimeoutException("timeout")
        with patch("src.escalation.escalation_engine.httpx.AsyncClient", return_value=mock_client), \
             patch("src.escalation.escalation_engine.IP_REPUTATION_API_URL", metadata_url), \
             patch("src.escalation.escalation_engine.ENABLE_IP_REPUTATION", True):
            result_timeout = await escalation_engine.check_ip_reputation("1.1.1.1")
            self.assertIsNone(result_timeout)

        bad_json_response = MagicMock()
        bad_json_response.raise_for_status.return_value = None
        bad_json_response.json.side_effect = json.JSONDecodeError("err", "", 0)
        bad_json_response.text = "<html>oops</html>"
        mock_client2 = AsyncMock()
        mock_client2.__aenter__.return_value.get.return_value = bad_json_response
        with patch("src.escalation.escalation_engine.httpx.AsyncClient", return_value=mock_client2), \
             patch("src.escalation.escalation_engine.IP_REPUTATION_API_URL", metadata_url), \
             patch("src.escalation.escalation_engine.ENABLE_IP_REPUTATION", True):
            result_json = await escalation_engine.check_ip_reputation("1.1.1.1")
            self.assertIsNone(result_json)

    async def test_classify_with_external_api_timeout_and_json_error(self):
        """External API classification should handle timeouts and JSON errors."""
        meta = escalation_engine.RequestMetadata(timestamp="2023-01-01T00:00:00Z", ip="1.1.1.1", source="test", method="GET")
        api_url = "http://example.com/api"
        # Timeout case
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post.side_effect = httpx.TimeoutException("timeout")
        with patch("src.escalation.escalation_engine.httpx.AsyncClient", return_value=mock_client), \
             patch("src.escalation.escalation_engine.EXTERNAL_API_URL", api_url):
            result_timeout = await escalation_engine.classify_with_external_api(meta)
            self.assertIsNone(result_timeout)

        # Bad JSON case
        bad_resp = MagicMock()
        bad_resp.raise_for_status.return_value = None
        bad_resp.json.side_effect = json.JSONDecodeError("err", "", 0)
        bad_resp.text = "<html>oops</html>"
        mock_client2 = AsyncMock()
        mock_client2.__aenter__.return_value.post.return_value = bad_resp
        with patch("src.escalation.escalation_engine.httpx.AsyncClient", return_value=mock_client2), \
             patch("src.escalation.escalation_engine.EXTERNAL_API_URL", api_url):
            result_json = await escalation_engine.classify_with_external_api(meta)
            self.assertIsNone(result_json)

    async def test_escalate_endpoint_bot_high_score_webhook(self):
        """Test a bot request with a high score that triggers a webhook."""
        with patch('escalation.escalation_engine.run_heuristic_and_model_analysis', return_value=0.95):
            response = self.client.post("/escalate", json={"timestamp": "2023-01-01T12:00:00Z", "ip": "2.2.2.2", "source": "test", "method": "GET"}, headers={"X-API-Key": "testkey"})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['action'], 'webhook_triggered_high_score')
        self.assertTrue(data['is_bot_decision'])
        self.mocks['forward_to_webhook'].assert_called_once()
        # Correctly check for the 'ip' inside the 'details' dictionary of the webhook payload
        self.assertEqual(self.mocks['forward_to_webhook'].call_args[0][0]['details']['ip'], '2.2.2.2')

    async def test_escalate_endpoint_ip_reputation_block(self):
        """Test a request that is immediately blocked by IP reputation."""
        self.mocks['check_ip_reputation'].return_value = {"is_malicious": True, "score": 99}
        with patch('escalation.escalation_engine.ENABLE_IP_REPUTATION', True):
            response = self.client.post("/escalate", json={"timestamp": "2023-01-01T12:00:00Z", "ip": "3.3.3.3", "source": "test", "method": "GET"}, headers={"X-API-Key": "testkey"})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['action'], 'webhook_triggered_ip_reputation')
        self.assertTrue(data['is_bot_decision'])
        self.mocks['forward_to_webhook'].assert_called_once()

    async def test_escalate_endpoint_local_llm_confirms_bot(self):
        """Test a request where the local LLM confirms a bot."""
        self.mocks['classify_with_local_llm_api'].return_value = True # Returns boolean True for bot
        with patch('escalation.escalation_engine.ENABLE_LOCAL_LLM_CLASSIFICATION', True), \
             patch('escalation.escalation_engine.run_heuristic_and_model_analysis', return_value=0.6): # Borderline score
            response = self.client.post("/escalate", json={"timestamp": "2023-01-01T12:00:00Z", "ip": "4.4.4.4", "source": "test", "method": "GET"}, headers={"X-API-Key": "testkey"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['action'], 'webhook_triggered_local_llm')
        self.assertTrue(data['is_bot_decision'])

    async def test_escalate_endpoint_external_api_confirms_human(self):
        """Test a borderline request where an external API confirms it's human."""
        self.mocks['classify_with_external_api'].return_value = False # Returns boolean False for human
        with patch('escalation.escalation_engine.ENABLE_EXTERNAL_API_CLASSIFICATION', True), \
             patch('escalation.escalation_engine.run_heuristic_and_model_analysis', return_value=0.7):
            response = self.client.post("/escalate", json={"timestamp": "2023-01-01T12:00:00Z", "ip": "5.5.5.5", "source": "test", "method": "GET"}, headers={"X-API-Key": "testkey"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['action'], 'classified_human_external_api')
        self.assertFalse(data['is_bot_decision'])

    async def test_escalate_endpoint_captcha_triggered(self):
        """Test a request where CAPTCHA is triggered."""
        with patch('escalation.escalation_engine.ENABLE_CAPTCHA_TRIGGER', True), \
             patch('escalation.escalation_engine.CAPTCHA_SCORE_THRESHOLD_LOW', 0.6), \
             patch('escalation.escalation_engine.CAPTCHA_SCORE_THRESHOLD_HIGH', 0.8), \
             patch('escalation.escalation_engine.run_heuristic_and_model_analysis', return_value=0.65):
            response = self.client.post("/escalate", json={"timestamp": "2023-01-01T12:00:00Z", "ip": "6.6.6.6", "source": "test", "method": "GET"}, headers={"X-API-Key": "testkey"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Correctly assert that the action is 'captcha_triggered', not 'captcha_passed'
        self.assertEqual(data['action'], 'captcha_triggered')
        # In the captcha flow, the final decision is deferred, so is_bot_decision should be None
        self.assertIsNone(data['is_bot_decision']) 
        self.mocks['trigger_captcha_challenge'].assert_called_once()
        self.mocks['forward_to_webhook'].assert_not_called()

    async def test_escalate_endpoint_invalid_ip(self):
        """IP addresses that can't be parsed should return 400."""
        response = self.client.post(
            "/escalate",
            json={"timestamp": "2023-01-01T12:00:00Z", "ip": "not-an-ip", "source": "test", "method": "GET"},
            headers={"X-API-Key": "testkey"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Invalid IP address")
        self.mocks['check_ip_reputation'].assert_not_called()

    async def test_escalate_endpoint_missing_api_key(self):
        """Requests without the required API key should be rejected."""
        with patch('src.escalation.escalation_engine.ESCALATION_API_KEY', 'testkey'):
            response = self.client.post(
                "/escalate",
                json={"timestamp": "2023-01-01T12:00:00Z", "ip": "7.7.7.7", "source": "test", "method": "GET"}
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Unauthorized")

    async def test_escalate_endpoint_incorrect_api_key(self):
        """Requests with an incorrect API key should be rejected."""
        with patch('src.escalation.escalation_engine.ESCALATION_API_KEY', 'testkey'):
            response = self.client.post(
                "/escalate",
                json={"timestamp": "2023-01-01T12:00:00Z", "ip": "8.8.8.8", "source": "test", "method": "GET"},
                headers={"X-API-Key": "wrong"}
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Unauthorized")


class TestExternalServiceFunctions(unittest.IsolatedAsyncioTestCase):
    """Direct tests for IP reputation and external classification helpers."""

    async def test_check_ip_reputation_timeout(self):
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.side_effect = httpx.TimeoutException("timeout")
        with patch('escalation.escalation_engine.httpx.AsyncClient', return_value=mock_client), \
             patch('escalation.escalation_engine.ENABLE_IP_REPUTATION', True), \
             patch('escalation.escalation_engine.IP_REPUTATION_API_URL', 'http://api'): \
            result = await escalation_engine.check_ip_reputation('1.1.1.1')

        self.assertIsNone(result)

    async def test_check_ip_reputation_json_error(self):
        mock_client = AsyncMock()
        fake_response = MagicMock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.side_effect = json.JSONDecodeError('bad', 'doc', 0)
        fake_response.text = 'bad json'
        mock_client.__aenter__.return_value.get.return_value = fake_response
        with patch('escalation.escalation_engine.httpx.AsyncClient', return_value=mock_client), \
             patch('escalation.escalation_engine.ENABLE_IP_REPUTATION', True), \
             patch('escalation.escalation_engine.IP_REPUTATION_API_URL', 'http://api'):
            result = await escalation_engine.check_ip_reputation('2.2.2.2')

        self.assertIsNone(result)

    async def test_classify_with_external_api_timeout(self):
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post.side_effect = httpx.TimeoutException("timeout")
        metadata = RequestMetadata(timestamp="2023-01-01T12:00:00Z", ip="3.3.3.3", source="test", method="GET")
        with patch('escalation.escalation_engine.httpx.AsyncClient', return_value=mock_client), \
             patch('escalation.escalation_engine.EXTERNAL_API_URL', 'http://api'):
            result = await escalation_engine.classify_with_external_api(metadata)

        self.assertIsNone(result)

    async def test_classify_with_external_api_json_error(self):
        mock_client = AsyncMock()
        fake_response = MagicMock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.side_effect = json.JSONDecodeError('bad', 'doc', 0)
        fake_response.text = 'bad json'
        mock_client.__aenter__.return_value.post.return_value = fake_response
        metadata = RequestMetadata(timestamp="2023-01-01T12:00:00Z", ip="4.4.4.4", source="test", method="GET")
        with patch('escalation.escalation_engine.httpx.AsyncClient', return_value=mock_client), \
             patch('escalation.escalation_engine.EXTERNAL_API_URL', 'http://api'):
            result = await escalation_engine.classify_with_external_api(metadata)

        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
