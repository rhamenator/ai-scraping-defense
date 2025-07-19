import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.tarpit import bad_api_generator


class TestBadApiGenerator(unittest.TestCase):
    def test_generate_bad_endpoints_count(self):
        endpoints = bad_api_generator.generate_bad_endpoints(count=3)
        self.assertEqual(len(endpoints), 3)
        self.assertEqual(len(set(endpoints)), 3)
        for ep in endpoints:
            self.assertTrue(ep.startswith("/"))

    def test_register_bad_endpoints(self):
        app = FastAPI()
        with patch('src.tarpit.bad_api_generator.log_honeypot_hit') as log_mock:
            eps = bad_api_generator.register_bad_endpoints(app, count=2)
            self.assertEqual(len(eps), 2)
            client = TestClient(app)
            resp = client.get(f"/api{eps[0]}")
            self.assertEqual(resp.status_code, 404)
            log_mock.assert_called()


if __name__ == '__main__':
    unittest.main()
