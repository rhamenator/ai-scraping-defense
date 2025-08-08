import importlib
import os
import tempfile
import unittest

from fastapi.testclient import TestClient


class TestPublicBlocklistAPI(unittest.TestCase):
    def setUp(self):
        self.tempfile = tempfile.NamedTemporaryFile(delete=False)
        self.tempfile.write(b'{"ips": []}')
        self.tempfile.close()
        self.env_patch = unittest.mock.patch.dict(
            os.environ,
            {
                "PUBLIC_BLOCKLIST_FILE": self.tempfile.name,
                "PUBLIC_BLOCKLIST_API_KEY": "secret",
            },
        )
        self.env_patch.start()
        import src.public_blocklist.public_blocklist_api as pb

        importlib.reload(pb)
        self.client = TestClient(pb.app)

    def tearDown(self):
        self.env_patch.stop()
        os.unlink(self.tempfile.name)

    def test_get_list_empty(self):
        resp = self.client.get("/list")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"ips": []})

    def test_report_ip_adds_entry(self):
        resp = self.client.post(
            "/report", json={"ip": "1.2.3.4"}, headers={"X-API-Key": "secret"}
        )
        self.assertEqual(resp.status_code, 200)
        resp2 = self.client.get("/list")
        self.assertEqual(resp2.json(), {"ips": ["1.2.3.4"]})

    def test_report_ip_bad_key(self):
        resp = self.client.post(
            "/report", json={"ip": "5.6.7.8"}, headers={"X-API-Key": "wrong"}
        )
        self.assertEqual(resp.status_code, 401)

    def test_report_ip_missing_key(self):
        resp = self.client.post("/report", json={"ip": "9.9.9.9"})
        self.assertEqual(resp.status_code, 401)
