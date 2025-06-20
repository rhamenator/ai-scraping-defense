# test/ai_service/ai_webhook.test.py
import unittest
from unittest.mock import patch, MagicMock
from ai_service import ai_webhook
import json
from fastapi.testclient import TestClient

class TestAIWebhookComprehensive(unittest.TestCase):

    def setUp(self):
        """Set up the FastAPI test client and patch dependencies."""
        self.client = TestClient(ai_webhook.app)

        self.redis_client_patcher = patch('ai_service.ai_webhook.get_redis_connection')
        self.mock_get_redis = self.redis_client_patcher.start()
        self.mock_redis_client = MagicMock()
        self.mock_get_redis.return_value = self.mock_redis_client

    def tearDown(self):
        """Stop all patches."""
        patch.stopall()

    def test_webhook_receiver_block_ip_success(self):
        """Test a successful 'block_ip' action."""
        payload = {
            "action": "block_ip",
            "ip": "10.0.0.1",
            "reason": "High bot score",
            "source": "escalation-engine"
        }
        self.mock_redis_client.sadd.return_value = 1
        response = self.client.post('/webhook', json=payload)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'status': 'success', 'message': 'IP 10.0.0.1 added to blocklist.'})
        self.mock_redis_client.sadd.assert_called_once_with('blocklist', '10.0.0.1')

    def test_webhook_receiver_allow_ip_success(self):
        """Test a successful 'allow_ip' action."""
        payload = {"action": "allow_ip", "ip": "20.0.0.2"}
        self.mock_redis_client.srem.return_value = 1
        response = self.client.post('/webhook', json=payload)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'status': 'success', 'message': 'IP 20.0.0.2 removed from blocklist.'})
        self.mock_redis_client.srem.assert_called_once_with('blocklist', '20.0.0.2')
        
    def test_webhook_receiver_flag_ip_success(self):
        """Test a successful 'flag_ip' action."""
        payload = {"action": "flag_ip", "ip": "30.0.0.3", "reason": "Suspicious activity"}
        self.mock_redis_client.set.return_value = True
        response = self.client.post('/webhook', json=payload)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'status': 'success', 'message': 'IP 30.0.0.3 flagged.'})
        self.mock_redis_client.set.assert_called_once_with('ip_flag:30.0.0.3', 'Suspicious activity')

    def test_webhook_receiver_unflag_ip_success(self):
        """Test a successful 'unflag_ip' action."""
        payload = {"action": "unflag_ip", "ip": "40.0.0.4"}
        self.mock_redis_client.delete.return_value = 1
        response = self.client.post('/webhook', json=payload)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'status': 'success', 'message': 'IP 40.0.0.4 unflagged.'})
        self.mock_redis_client.delete.assert_called_once_with('ip_flag:40.0.0.4')

    def test_webhook_receiver_invalid_action(self):
        """Test that an unsupported action returns a 400 error."""
        payload = {"action": "reboot_server", "ip": "1.2.3.4"}
        response = self.client.post('/webhook', json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid action", response.json()['error'])

    def test_webhook_receiver_payload_missing_ip(self):
        """Test that a payload missing the 'ip' field returns a 400 error."""
        payload = {"action": "block_ip", "reason": "No IP here."}
        response = self.client.post('/webhook', json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], "Missing 'ip' in payload for action 'block_ip'.")

    def test_webhook_receiver_redis_unavailable(self):
        """Test that a 503 error is returned if the Redis connection fails."""
        self.mock_get_redis.return_value = None
        payload = {"action": "block_ip", "ip": "1.2.3.4"}
        response = self.client.post('/webhook', json=payload)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error'], 'Redis service unavailable')

    @patch('ai_service.ai_webhook.logger.error')
    def test_webhook_receiver_redis_command_fails(self, mock_logger_error):
        """Test that a 500 error is returned if a Redis command fails."""
        self.mock_redis_client.sadd.side_effect = Exception("Redis command failed")
        payload = {"action": "block_ip", "ip": "1.2.3.4"}
        response = self.client.post('/webhook', json=payload)
        
        self.assertEqual(response.status_code, 500)
        self.assertIn("Failed to execute action", response.json()['error'])
        mock_logger_error.assert_called_once()

    def test_health_check_healthy(self):
        """Test the health check endpoint when Redis is connected."""
        self.mock_redis_client.ping.return_value = True
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'status': 'ok', 'redis_connected': True})

    def test_health_check_unhealthy(self):
        """Test the health check endpoint when Redis is not connected."""
        self.mock_get_redis.return_value = None
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json, {'status': 'error', 'redis_connected': False})

if __name__ == '__main__':
    unittest.main()
