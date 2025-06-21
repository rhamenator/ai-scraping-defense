# test/tarpit/tarpit_api.test.py
import unittest
from unittest.mock import patch, MagicMock, AsyncMock, ANY
from fastapi.testclient import TestClient
import httpx

from tarpit.tarpit_api import app

class TestTarpitAPIComprehensive(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """Set up test client and patch all external dependencies."""
        self.client = TestClient(app)
        
        self.patches = {
            'log_honeypot_hit': patch('tarpit.tarpit_api.log_honeypot_hit'),
            'flag_suspicious_ip': patch('tarpit.tarpit_api.flag_suspicious_ip'),
            'generate_dynamic_tarpit_page': patch('tarpit.tarpit_api.generate_dynamic_tarpit_page', return_value="<html>Mock Tarpit Page</html>"),
            'get_redis_connection': patch('tarpit.tarpit_api.get_redis_connection'),
            'trigger_ip_block': patch('tarpit.tarpit_api.trigger_ip_block'),
            'httpx.AsyncClient': patch('tarpit.tarpit_api.httpx.AsyncClient')
        }
        self.mocks = {name: p.start() for name, p in self.patches.items()}

        # Configure mock Redis clients
        self.mock_redis_hops = MagicMock()
        self.mock_redis_blocklist = MagicMock()
        self.mocks['get_redis_connection'].side_effect = [
            self.mock_redis_hops, self.mock_redis_blocklist
        ]
        
        # Configure mock AsyncClient
        self.async_client_instance = AsyncMock()
        self.async_client_instance.__aenter__.return_value.post = AsyncMock()
        self.mocks['httpx.AsyncClient'].return_value = self.async_client_instance

    def tearDown(self):
        """Stop all patches."""
        for p in self.patches.values():
            p.stop()

    async def test_tarpit_handler_normal_flow(self):
        """Test the standard flow: log, flag, escalate, and serve content."""
        # Mock Redis pipeline for hop check (not exceeding limit)
        mock_pipeline = self.mock_redis_hops.pipeline.return_value
        mock_pipeline.execute.return_value = [10, True]  # Hop count is 10

        response = self.client.get("/tarpit/some/path", headers={"User-Agent": "TestBot"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "<html>Mock Tarpit Page</html>")
        
        # Verify all actions were taken
        self.mocks['log_honeypot_hit'].assert_called_once()
        self.mocks['flag_suspicious_ip'].assert_called_once_with('testclient', ANY)
        self.mocks['httpx.AsyncClient'].__aenter__.return_value.post.assert_called_once()
        self.mocks['generate_dynamic_tarpit_page'].assert_called_once()
        self.mocks['trigger_ip_block'].assert_not_called()

    async def test_tarpit_handler_hop_limit_exceeded(self):
        """Test that the request is blocked and reported if the hop limit is exceeded."""
        mock_pipeline = self.mock_redis_hops.pipeline.return_value
        mock_pipeline.execute.return_value = [300, True]  # Hop count exceeds default of 250
        
        with patch('tarpit.tarpit_api.TAR_PIT_MAX_HOPS', 250), patch('tarpit.tarpit_api.HOP_LIMIT_ENABLED', True):
            response = self.client.get("/tarpit/blocked/path")

        self.assertEqual(response.status_code, 403)
        self.assertIn("Access Denied", response.text)
        self.mocks['trigger_ip_block'].assert_called_once_with("testclient", ANY)
        
        # Ensure other actions are NOT taken
        self.mocks['log_honeypot_hit'].assert_not_called()
        self.mocks['generate_dynamic_tarpit_page'].assert_not_called()

    async def test_tarpit_handler_escalation_fails_gracefully(self):
        """Test that the tarpit still serves content even if escalation to the AI service fails."""
        self.async_client_instance.__aenter__.return_value.post.side_effect = httpx.RequestError("Connection failed")
        mock_pipeline = self.mock_redis_hops.pipeline.return_value
        mock_pipeline.execute.return_value = [15, True]
        
        with self.assertLogs('tarpit.tarpit_api', level='ERROR') as cm:
            response = self.client.get("/tarpit/fail/path")
            self.assertIn("Error escalating request", cm.output[0])
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "<html>Mock Tarpit Page</html>")
        # All other actions besides escalation should have happened
        self.mocks['log_honeypot_hit'].assert_called_once()
        self.mocks['generate_dynamic_tarpit_page'].assert_called_once()

    def test_health_check_healthy(self):
        """Test the health check endpoint when all dependencies are healthy."""
        self.mock_redis_hops.ping.return_value = True
        self.mock_redis_blocklist.ping.return_value = True
        
        with patch('tarpit.tarpit_api.GENERATOR_AVAILABLE', True):
            response = self.client.get("/health")
            
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['redis_hops_connected'])
        self.assertTrue(data['redis_blocklist_connected'])
        self.assertTrue(data['markov_generator_available'])

    def test_health_check_redis_unhealthy(self):
        """Test the health check when a Redis instance is unavailable."""
        self.mock_redis_hops.ping.return_value = True
        self.mock_redis_blocklist.ping.side_effect = ConnectionError
        
        response = self.client.get("/health")
        
        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data['status'], 'error')
        self.assertTrue(data['redis_hops_connected'])
        self.assertFalse(data['redis_blocklist_connected'])

if __name__ == '__main__':
    unittest.main()
