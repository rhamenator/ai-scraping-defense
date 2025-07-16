# test/escalation/escalation_engine.test.py
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import datetime
import json
from fastapi.testclient import TestClient
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

    def tearDown(self):
        """Stop all patches."""
        for patcher in self.patchers.values():
            patcher.stop()

    def test_request_metadata_validation(self):
        """Test RequestMetadata Pydantic model validation."""
        # Correctly added 'headers' to satisfy the model's type hints
        valid_data = {"timestamp": "2023-01-01T12:00:00Z", "ip": "1.1.1.1", "source": "test", "headers": None}
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
            path="/wp-admin"
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
            response = self.client.post("/escalate", json={"timestamp": "2023-01-01T12:00:00Z", "ip": "1.1.1.1", "source": "test"})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['action'], 'classified_human_low_score')
        self.assertFalse(data['is_bot_decision'])
        self.mocks['forward_to_webhook'].assert_not_called()

    async def test_escalate_endpoint_bot_high_score_webhook(self):
        """Test a bot request with a high score that triggers a webhook."""
        with patch('escalation.escalation_engine.run_heuristic_and_model_analysis', return_value=0.95):
            response = self.client.post("/escalate", json={"timestamp": "2023-01-01T12:00:00Z", "ip": "2.2.2.2", "source": "test"})
        
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
            response = self.client.post("/escalate", json={"timestamp": "2023-01-01T12:00:00Z", "ip": "3.3.3.3", "source": "test"})
        
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
            response = self.client.post("/escalate", json={"timestamp": "2023-01-01T12:00:00Z", "ip": "4.4.4.4", "source": "test"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['action'], 'webhook_triggered_local_llm')
        self.assertTrue(data['is_bot_decision'])

    async def test_escalate_endpoint_external_api_confirms_human(self):
        """Test a borderline request where an external API confirms it's human."""
        self.mocks['classify_with_external_api'].return_value = False # Returns boolean False for human
        with patch('escalation.escalation_engine.ENABLE_EXTERNAL_API_CLASSIFICATION', True), \
             patch('escalation.escalation_engine.run_heuristic_and_model_analysis', return_value=0.7):
            response = self.client.post("/escalate", json={"timestamp": "2023-01-01T12:00:00Z", "ip": "5.5.5.5", "source": "test"})

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
            response = self.client.post("/escalate", json={"timestamp": "2023-01-01T12:00:00Z", "ip": "6.6.6.6", "source": "test"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Correctly assert that the action is 'captcha_triggered', not 'captcha_passed'
        self.assertEqual(data['action'], 'captcha_triggered')
        # In the captcha flow, the final decision is deferred, so is_bot_decision should be None
        self.assertIsNone(data['is_bot_decision']) 
        self.mocks['trigger_captcha_challenge'].assert_called_once()
        self.mocks['forward_to_webhook'].assert_not_called()

if __name__ == '__main__':
    unittest.main()
