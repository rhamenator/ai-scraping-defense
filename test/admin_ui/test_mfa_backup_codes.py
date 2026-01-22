import os
import unittest
from unittest.mock import patch

import bcrypt
import pyotp
from fastapi.testclient import TestClient

from src.admin_ui import admin_ui, auth, mfa


class MockRedis:
    def __init__(self):
        self.store = {}
        self.expiry = {}
        self.lists = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        if ex is not None:
            self.expiry[key] = ex
        return True

    def ttl(self, key):
        return self.expiry.get(key, -1)

    def incr(self, key):
        current = int(self.store.get(key, 0))
        current += 1
        self.store[key] = current
        return current

    def expire(self, key, ttl):
        self.expiry[key] = ttl
        return True

    def delete(self, key):
        self.store.pop(key, None)
        self.expiry.pop(key, None)
        self.lists.pop(key, None)

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)
        return len(self.lists[key])

    def lrange(self, key, start, end):
        items = self.lists.get(key, [])
        if end == -1:
            end = len(items) - 1
        return items[start : end + 1]

    def ltrim(self, key, start, end):
        items = self.lists.get(key, [])
        if end == -1:
            end = len(items) - 1
        self.lists[key] = items[start : end + 1]

    def lrem(self, key, count, value):
        items = self.lists.get(key, [])
        removed = 0
        if count == 0:
            self.lists[key] = [item for item in items if item != value]
            removed = len(items) - len(self.lists[key])
        else:
            remaining = []
            for item in items:
                if item == value and removed < abs(count):
                    removed += 1
                    continue
                remaining.append(item)
            self.lists[key] = remaining
        return removed

    def getdel(self, key):
        value = self.get(key)
        self.delete(key)
        return value

    def scan_iter(self, match=None, count=1):
        return iter([])


class TestAdminUIMfaBackupCodes(unittest.TestCase):
    def setUp(self):
        os.environ["ADMIN_UI_USERNAME"] = "admin"
        os.environ["ADMIN_UI_PASSWORD_HASH"] = bcrypt.hashpw(
            b"testpass", bcrypt.gensalt()
        ).decode()
        os.environ["ADMIN_UI_ROLE"] = "admin"
        os.environ["ADMIN_UI_2FA_SECRET"] = pyotp.random_base32()
        auth.ADMIN_UI_ROLE = "admin"
        self.client = TestClient(admin_ui.app)
        self.auth = ("admin", "testpass")

    def _totp_headers(self) -> dict:
        secret = os.environ["ADMIN_UI_2FA_SECRET"]
        return {"X-2FA-Code": pyotp.TOTP(secret).now()}

    def test_backup_code_allows_auth(self):
        mock_redis = MockRedis()
        with patch("src.admin_ui.auth.get_redis_connection", return_value=mock_redis):
            with patch(
                "src.admin_ui.mfa.get_redis_connection", return_value=mock_redis
            ):
                codes = mfa.generate_backup_codes(count=1)
                self.assertTrue(mfa.store_backup_codes("admin", codes))
                headers = {"X-2FA-Backup-Code": codes[0]}
                response = self.client.get("/", auth=self.auth, headers=headers)
                self.assertEqual(response.status_code, 200)

    def test_backup_code_rejected_when_invalid(self):
        mock_redis = MockRedis()
        with patch("src.admin_ui.auth.get_redis_connection", return_value=mock_redis):
            with patch(
                "src.admin_ui.mfa.get_redis_connection", return_value=mock_redis
            ):
                codes = mfa.generate_backup_codes(count=1)
                self.assertTrue(mfa.store_backup_codes("admin", codes))
                headers = {"X-2FA-Backup-Code": "00000000"}
                response = self.client.get("/", auth=self.auth, headers=headers)
                self.assertEqual(response.status_code, 401)

    def test_generate_backup_codes_endpoint(self):
        mock_redis = MockRedis()
        with patch("src.admin_ui.auth.get_redis_connection", return_value=mock_redis):
            with patch(
                "src.admin_ui.mfa.get_redis_connection", return_value=mock_redis
            ):
                response = self.client.post(
                    "/mfa/backup-codes",
                    auth=self.auth,
                    headers=self._totp_headers(),
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["backup_codes"])
