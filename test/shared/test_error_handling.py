import unittest

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from src.shared.middleware import create_app


class _Item(BaseModel):
    name: str


class TestErrorHandling(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

        @self.app.get("/boom")
        def boom():
            raise HTTPException(status_code=400, detail="Invalid payload")

        @self.app.post("/items")
        def create_item(item: _Item):
            return {"status": "ok", "name": item.name}

        self.client = TestClient(self.app)

    def test_http_exception_envelope(self):
        resp = self.client.get("/boom")
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertEqual(data["detail"], "Invalid payload")
        self.assertEqual(data["error"]["code"], "invalid_request")
        self.assertIn("request_id", data)
        self.assertEqual(resp.headers.get("X-Request-ID"), data["request_id"])

    def test_request_id_passthrough(self):
        resp = self.client.get("/boom", headers={"X-Request-ID": "req-123"})
        data = resp.json()
        self.assertEqual(data["request_id"], "req-123")
        self.assertEqual(resp.headers.get("X-Request-ID"), "req-123")

    def test_validation_error_envelope(self):
        resp = self.client.post("/items", json={"name": 123})
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertEqual(data["error"]["code"], "validation_error")
        self.assertEqual(data["detail"], "Validation error")
        self.assertTrue(data["error"]["details"])


if __name__ == "__main__":
    unittest.main()
