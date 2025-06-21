# test/admin_ui/admin_ui.test.py
import unittest
import json
from unittest.mock import patch, MagicMock
from admin_ui.admin_ui import app

class TestAdminUIComprehensive(unittest.TestCase):

    def setUp(self):
        """Set up the test client for the Flask app."""
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_index_route_success(self):
        """Test the main dashboard page serves HTML correctly and contains key elements."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'AI Scraping Defense - Admin Dashboard', response.data)
        self.assertIn(b'id="metrics-container"', response.data)
        self.assertIn(b'id="blocklist-container"', response.data)
        self.assertIn(b'id="manual-ip-block"', response.data)

    @patch('admin_ui.admin_ui._get_metrics_dict_func')
    def test_metrics_endpoint_success(self, mock_get_metrics_dict):
        """Test the /metrics endpoint with valid, complex Prometheus-formatted data."""
        mock_get_metrics_dict.return_value = {
            'requests_total{method="GET"}': 150.0,
            'requests_total{method="POST"}': 50.0,
            'bots_detected_total': 25.0,
            'active_connections': 10.0
        }
        
        with patch('admin_ui.admin_ui.METRICS_TRULY_AVAILABLE', True):
            response = self.client.get('/metrics')
        
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['requests_total{method="GET"}'], 150.0)
        self.assertEqual(data['bots_detected_total'], 25.0)

    @patch('admin_ui.admin_ui.METRICS_TRULY_AVAILABLE', False)
    def test_metrics_endpoint_module_unavailable(self):
        """Test the /metrics endpoint when the metrics module is flagged as unavailable."""
        response = self.client.get('/metrics')
        self.assertEqual(response.status_code, 503)
        data = response.get_json()
        self.assertEqual(data.get('error'), 'Metrics module not available')

    @patch('admin_ui.admin_ui._get_metrics_dict_func', return_value={'error': 'Parsing failed'})
    def test_metrics_endpoint_parsing_error(self, mock_get_metrics_dict):
        """Test the /metrics endpoint when parsing the Prometheus data fails."""
        with patch('admin_ui.admin_ui.METRICS_TRULY_AVAILABLE', True):
            response = self.client.get('/metrics')
        
        self.assertEqual(response.status_code, 500)
        data = response.get_json()
        self.assertIn('error', data)
        self.assertEqual(data['error'], 'Parsing failed')

    @patch('admin_ui.admin_ui.get_redis_connection')
    def test_get_blocklist_success(self, mock_get_redis):
        """Test successfully retrieving the blocklist from Redis."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.smembers.return_value = {'1.1.1.1', '2.2.2.2'}
        mock_get_redis.return_value = mock_redis_instance

        response = self.client.get('/blocklist')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('1.1.1.1', data)
        self.assertIn('2.2.2.2', data)
        self.assertEqual(len(data), 2)

    @patch('admin_ui.admin_ui.get_redis_connection', return_value=None)
    def test_get_blocklist_redis_unavailable(self, mock_get_redis):
        """Test the /blocklist endpoint when Redis is unavailable."""
        response = self.client.get('/blocklist')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json, {'error': 'Redis service unavailable'})

    @patch('admin_ui.admin_ui.get_redis_connection')
    def test_block_ip_success(self, mock_get_redis):
        """Test manually blocking an IP address."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.sadd.return_value = 1 # Simulate adding a new member
        mock_get_redis.return_value = mock_redis_instance

        response = self.client.post('/block', data=json.dumps({'ip': '3.3.3.3'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'status': 'success', 'ip': '3.3.3.3'})
        mock_redis_instance.sadd.assert_called_once_with('blocklist', '3.3.3.3')

    @patch('admin_ui.admin_ui.get_redis_connection')
    def test_unblock_ip_success(self, mock_get_redis):
        """Test manually unblocking an IP address."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.srem.return_value = 1 # Simulate removing a member
        mock_get_redis.return_value = mock_redis_instance

        response = self.client.post('/unblock', data=json.dumps({'ip': '1.1.1.1'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'status': 'success', 'ip': '1.1.1.1'})
        mock_redis_instance.srem.assert_called_once_with('blocklist', '1.1.1.1')
        
    def test_block_ip_invalid_payload(self):
        """Test the /block endpoint with an invalid payload."""
        response = self.client.post('/block', data=json.dumps({'address': '3.3.3.3'}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json, {'error': 'Invalid request, missing ip'})

if __name__ == '__main__':
    unittest.main()
