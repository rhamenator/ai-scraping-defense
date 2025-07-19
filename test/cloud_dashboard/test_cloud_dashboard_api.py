import unittest
from fastapi.testclient import TestClient
import importlib

from src.cloud_dashboard import cloud_dashboard_api as cd

class TestCloudDashboardAPI(unittest.TestCase):
    def setUp(self):
        importlib.reload(cd)
        self.client = TestClient(cd.app)

    def test_register_and_push_metrics(self):
        resp = self.client.post('/register', json={'installation_id': 'inst1'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'registered')

        data = {'installation_id': 'inst1', 'metrics': {'requests': 5}}
        resp = self.client.post('/push', json=data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'ok')

        resp = self.client.get('/metrics/inst1')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'requests': 5})

    def test_push_invalid_payload(self):
        resp = self.client.post('/push', json={'installation_id': 'x'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.json())

    def test_websocket_streams_metrics(self):
        self.client.post('/register', json={'installation_id': 'ws1'})
        with self.client.websocket_connect('/ws/ws1') as ws:
            first = ws.receive_json()
            self.assertEqual(first, {})
            self.client.post('/push', json={'installation_id': 'ws1', 'metrics': {'m': 1}})
            data = ws.receive_json()
            self.assertEqual(data, {'m': 1})

if __name__ == '__main__':
    unittest.main()
