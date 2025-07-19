# test/admin_ui/test_admin_ui.py
import unittest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from src.admin_ui import admin_ui

class TestAdminUIComprehensive(unittest.TestCase):

    def setUp(self):
        """Set up the test client for the FastAPI app."""
        self.client = TestClient(admin_ui.app)

    def test_index_route_success(self):
        """Test the main dashboard page serves HTML correctly and contains key elements."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        content = response.content
        self.assertIn(b'AI Scraping Defense - Admin Dashboard', content)
        self.assertIn(b'id="metrics-container"', content)
        self.assertIn(b'id="blocklist-container"', content)
        self.assertIn(b'id="manual-ip-block"', content)
        self.assertIn(b'admin.js', content)

    @patch('src.admin_ui.admin_ui._get_metrics_dict_func')
    def test_metrics_endpoint_success(self, mock_get_metrics_dict):
        """Test the /metrics endpoint with valid, complex Prometheus-formatted data."""
        mock_get_metrics_dict.return_value = {
            'requests_total{method="GET"}': 150.0,
            'requests_total{method="POST"}': 50.0,
            'bots_detected_total': 25.0,
            'active_connections': 10.0
        }
        
        with patch('src.admin_ui.admin_ui.METRICS_TRULY_AVAILABLE', True):
            response = self.client.get('/metrics')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['requests_total{method="GET"}'], 150.0)
        self.assertEqual(data['bots_detected_total'], 25.0)

    @patch('src.admin_ui.admin_ui.METRICS_TRULY_AVAILABLE', False)
    def test_metrics_endpoint_module_unavailable(self):
        """Test the /metrics endpoint when the metrics module is flagged as unavailable."""
        response = self.client.get('/metrics')
        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data.get('error'), 'Metrics module not available')

    @patch('src.admin_ui.admin_ui._get_metrics_dict_func', return_value={'error': 'Parsing failed'})
    def test_metrics_endpoint_parsing_error(self, mock_get_metrics_dict):
        """Test the /metrics endpoint when parsing the Prometheus data fails."""
        with patch('src.admin_ui.admin_ui.METRICS_TRULY_AVAILABLE', True):
            response = self.client.get('/metrics')
        
        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertIn('error', data)
        self.assertEqual(data['error'], 'Parsing failed')

    @patch('src.admin_ui.admin_ui.get_redis_connection')
    def test_get_blocklist_success(self, mock_get_redis):
        """Test successfully retrieving the blocklist from Redis."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.smembers.return_value = {'1.1.1.1', '2.2.2.2'}
        mock_get_redis.return_value = mock_redis_instance

        response = self.client.get('/blocklist')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('1.1.1.1', data)
        self.assertIn('2.2.2.2', data)
        self.assertEqual(len(data), 2)

    @patch('src.admin_ui.admin_ui.get_redis_connection', return_value=None)
    def test_get_blocklist_redis_unavailable(self, mock_get_redis):
        """Test the /blocklist endpoint when Redis is unavailable."""
        response = self.client.get('/blocklist')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'error': 'Redis service unavailable'})

    @patch('src.admin_ui.admin_ui.get_redis_connection')
    def test_block_ip_success(self, mock_get_redis):
        """Test manually blocking an IP address."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.sadd.return_value = 1 # Simulate adding a new member
        mock_get_redis.return_value = mock_redis_instance

        response = self.client.post('/block', json={'ip': '3.3.3.3'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'success', 'ip': '3.3.3.3'})
        mock_redis_instance.sadd.assert_called_once_with('blocklist', '3.3.3.3')

    @patch('src.admin_ui.admin_ui.get_redis_connection')
    def test_unblock_ip_success(self, mock_get_redis):
        """Test manually unblocking an IP address."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.srem.return_value = 1 # Simulate removing a member
        mock_get_redis.return_value = mock_redis_instance

        response = self.client.post('/unblock', json={'ip': '1.1.1.1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'success', 'ip': '1.1.1.1'})
        mock_redis_instance.srem.assert_called_once_with('blocklist', '1.1.1.1')
        
    def test_block_ip_invalid_payload(self):
        """Test the /block endpoint with an invalid payload."""
        response = self.client.post('/block', json={'address': '3.3.3.3'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'Invalid request, missing ip'})

    @patch('src.admin_ui.admin_ui._get_metrics_dict_func')
    def test_metrics_websocket_initial_message(self, mock_get_metrics):
        """Ensure the /ws/metrics endpoint streams metrics on connect."""
        mock_get_metrics.return_value = {'active_connections': 5}
        with self.client.websocket_connect('/ws/metrics') as websocket:
            data = websocket.receive_json()
        self.assertEqual(data, {'active_connections': 5})
        mock_get_metrics.assert_called()

    @patch('src.admin_ui.admin_ui.METRICS_TRULY_AVAILABLE', False)
    def test_metrics_websocket_module_unavailable(self):
        """WebSocket should send an error if metrics are unavailable."""
        with self.client.websocket_connect('/ws/metrics') as websocket:
            data = websocket.receive_json()
        self.assertEqual(data, {'error': 'Metrics module not available'})

    @patch('src.admin_ui.admin_ui._get_metrics_dict_func')
    @patch('src.admin_ui.admin_ui.get_redis_connection')
    @patch('src.admin_ui.admin_ui._load_recent_block_events_func')
    def test_block_stats_success(self, mock_load, mock_get_redis, mock_get_metrics):
        """Test the /block_stats endpoint aggregates data correctly."""
        mock_get_metrics.return_value = {
            'bots_detected_high_score_total': 10.0,
            'humans_detected_low_score_total': 5.0
        }
        mock_redis = MagicMock()
        mock_redis.smembers.return_value = {'4.4.4.4'}
        mock_redis.keys.return_value = ['blocklist:ip:4.4.4.4', 'blocklist:ip:5.5.5.5']
        mock_get_redis.return_value = mock_redis
        mock_load.return_value = [{'ip': '4.4.4.4', 'reason': 'test', 'timestamp': '2025-01-01T00:00:00Z'}]

        response = self.client.get('/block_stats')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['blocked_ip_count'], 1)
        self.assertEqual(data['temporary_block_count'], 2)
        self.assertEqual(data['total_bots_detected'], 10.0)
        self.assertEqual(data['total_humans_detected'], 5.0)
        self.assertEqual(len(data['recent_block_events']), 1)

    @patch('src.admin_ui.admin_ui._get_metrics_dict_func', side_effect=Exception('fail'))
    @patch('src.admin_ui.admin_ui.get_redis_connection', return_value=None)
    @patch('src.admin_ui.admin_ui._load_recent_block_events_func', return_value=[])
    def test_block_stats_handles_errors(self, mock_load, mock_get_redis, mock_get_metrics):
        """Test /block_stats handles missing data gracefully."""
        response = self.client.get('/block_stats')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['blocked_ip_count'], 0)
        self.assertEqual(data['temporary_block_count'], 0)
        self.assertEqual(data['total_bots_detected'], 0)
        self.assertEqual(data['total_humans_detected'], 0)

if __name__ == '__main__':
    unittest.main()
