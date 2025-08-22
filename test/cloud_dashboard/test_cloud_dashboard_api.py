import importlib
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.cloud_dashboard import cloud_dashboard_api as cd


class TestCloudDashboardAPI(unittest.TestCase):
    def setUp(self):
        importlib.reload(cd)

        class MockRedis:
            def __init__(self):
                self.store = {}

            def set(self, key, value, ex=None):
                self.store[key] = value

            def get(self, key):
                return self.store.get(key)

        self.mock_redis = MockRedis()
        patcher = patch(
            "src.cloud_dashboard.cloud_dashboard_api.get_redis_connection",
            return_value=self.mock_redis,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.client = TestClient(cd.app)

    def test_register_and_push_metrics(self):
        resp = self.client.post("/register", json={"installation_id": "inst1"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "registered")

        data = {"installation_id": "inst1", "metrics": {"requests": 5}}
        resp = self.client.post("/metrics", json=data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

        resp = self.client.get("/metrics/inst1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"requests": 5})

    def test_push_invalid_payload(self):
        resp = self.client.post("/metrics", json={"installation_id": "x"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_websocket_streams_metrics(self):
        self.client.post("/register", json={"installation_id": "ws1"})
        with self.client.websocket_connect("/ws/ws1") as ws:
            first = ws.receive_json()
            self.assertEqual(first, {})
            self.client.post(
                "/metrics", json={"installation_id": "ws1", "metrics": {"m": 1}}
            )
            data = ws.receive_json()
            self.assertEqual(data, {"m": 1})

    def test_api_key_enforced_when_configured(self):
        with patch.dict(os.environ, {"CLOUD_DASHBOARD_API_KEY": "sek"}):
            importlib.reload(cd)

            class MockRedis:
                def __init__(self):
                    self.store = {}

                def set(self, key, value, ex=None):
                    self.store[key] = value

                def get(self, key):
                    return self.store.get(key)

            mock_redis = MockRedis()
            with patch(
                "src.cloud_dashboard.cloud_dashboard_api.get_redis_connection",
                return_value=mock_redis,
            ):
                client = TestClient(cd.app)
                resp = client.post("/register", json={"installation_id": "x"})
                self.assertEqual(resp.status_code, 401)
                resp = client.post(
                    "/register",
                    json={"installation_id": "x"},
                    headers={"X-API-Key": "sek"},
                )
                self.assertEqual(resp.status_code, 200)
                resp = client.post(
                    "/metrics",
                    json={"installation_id": "x", "metrics": {}},
                    headers={"X-API-Key": "sek"},
                )
                self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
