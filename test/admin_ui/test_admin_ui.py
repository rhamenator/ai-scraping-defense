# test/admin_ui/test_admin_ui.py
import json
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import bcrypt
import pyotp
from fastapi.testclient import TestClient

from src.admin_ui import admin_ui, auth, blocklist, metrics, webauthn


class TestAdminUIComprehensive(unittest.TestCase):

    def setUp(self):
        """Set up the test client for the FastAPI app."""
        os.environ["ADMIN_UI_USERNAME"] = "admin"
        os.environ["ADMIN_UI_PASSWORD_HASH"] = bcrypt.hashpw(
            b"testpass", bcrypt.gensalt()
        ).decode()
        os.environ["ADMIN_UI_ROLE"] = "admin"
        os.environ["ADMIN_UI_2FA_SECRET"] = "JBSWY3DPEHPK3PXP"
        auth.ADMIN_UI_ROLE = "admin"
        # Disable rate limiting by making the auth layer think Redis is unavailable
        patcher = patch("src.admin_ui.auth.get_redis_connection", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.client = TestClient(admin_ui.app)
        self.auth = ("admin", "testpass")

    class _FakeRedis:
        def __init__(self):
            self.store = {}

        def hget(self, key, field):
            return self.store.get((key, field))

        def hset(self, key, field, value):
            self.store[(key, field)] = value
            return 1

    def _totp_headers(self) -> dict:
        secret = os.environ["ADMIN_UI_2FA_SECRET"]
        return {"X-2FA-Code": pyotp.TOTP(secret).now()}

    def test_reject_wildcard_cors_origin(self):
        """Wildcard CORS origin should be rejected when credentials are allowed."""
        with patch.dict(os.environ, {"ADMIN_UI_CORS_ORIGINS": "*"}):
            with self.assertRaises(ValueError):
                admin_ui._get_allowed_origins()

    def test_cors_methods_validate_override(self):
        """List-based method configuration should parse allowed verbs."""
        with patch.dict(os.environ, {"ADMIN_UI_CORS_METHODS": "GET, POST"}):
            self.assertEqual(
                admin_ui._get_allowed_methods(),
                ["GET", "POST"],
            )

    def test_cors_methods_reject_wildcard(self):
        """Wildcard methods should be rejected."""
        with patch.dict(os.environ, {"ADMIN_UI_CORS_METHODS": "*"}):
            with self.assertRaises(ValueError):
                admin_ui._get_allowed_methods()

    def test_cors_headers_validate_override(self):
        """Custom header list should be preserved in order."""
        with patch.dict(
            os.environ,
            {"ADMIN_UI_CORS_HEADERS": "X-Test, Content-Type"},
        ):
            self.assertEqual(
                admin_ui._get_allowed_headers(),
                ["X-Test", "Content-Type"],
            )

    def test_cors_headers_reject_wildcard(self):
        """Wildcard headers should be rejected."""
        with patch.dict(os.environ, {"ADMIN_UI_CORS_HEADERS": "*"}):
            with self.assertRaises(ValueError):
                admin_ui._get_allowed_headers()

    def test_update_webauthn_attachment_setting(self):
        """Admin settings should persist WebAuthn attachment preference."""
        fake_redis = self._FakeRedis()
        with patch(
            "src.admin_ui.admin_ui.get_redis_connection", return_value=fake_redis
        ):
            response = self.client.get(
                "/settings", auth=self.auth, headers=self._totp_headers()
            )
            self.assertEqual(response.status_code, 200)
            csrf_token = response.cookies.get("csrf_token")
            self.assertIsNotNone(csrf_token)

            form = {
                "csrf_token": csrf_token,
                "WEBAUTHN_AUTHENTICATOR_ATTACHMENT": "platform",
            }
            response = self.client.post(
                "/settings",
                auth=self.auth,
                headers=self._totp_headers(),
                cookies={"csrf_token": csrf_token},
                data=form,
            )
            self.assertEqual(response.status_code, 200)
            stored = fake_redis.store.get(
                (admin_ui.RUNTIME_SETTINGS_KEY, "WEBAUTHN_AUTHENTICATOR_ATTACHMENT")
            )
            self.assertEqual(stored, "platform")
            self.assertEqual(
                os.environ.get("WEBAUTHN_AUTHENTICATOR_ATTACHMENT"), "platform"
            )

    def test_settings_page_shows_security_kpis(self):
        """Settings page should render security KPI summaries."""
        fake_redis = self._FakeRedis()
        with patch(
            "src.admin_ui.admin_ui.get_redis_connection", return_value=fake_redis
        ):
            with patch(
                "src.admin_ui.admin_ui.metrics.get_security_kpis",
                return_value={"security_events_total": 5.0},
            ):
                response = self.client.get(
                    "/settings", auth=self.auth, headers=self._totp_headers()
                )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Security KPIs", response.content)
        self.assertIn(b"security_events_total", response.content)

    def test_index_route_success(self):
        """Test the main dashboard page serves HTML correctly and contains key elements."""
        response = self.client.get("/", auth=self.auth, headers=self._totp_headers())
        self.assertEqual(response.status_code, 200)
        content = response.content
        self.assertIn(b"AI Scraping Defense - Admin Dashboard", content)
        self.assertIn(b'id="metrics-container"', content)
        self.assertIn(b'id="blocklist-container"', content)
        self.assertIn(b'id="manual-ip-block"', content)
        self.assertIn(b"admin.js", content)
        self.assertEqual(
            response.headers.get("content-security-policy"), "default-src 'self'"
        )

    def test_auth_rate_limit_blocks_excess_requests(self):
        class MockRedis:
            def __init__(self):
                self.store = {}

            def incr(self, key):
                self.store[key] = self.store.get(key, 0) + 1
                return self.store[key]

            def expire(self, key, ttl):
                pass

        mock_redis = MockRedis()
        headers = self._totp_headers()
        with patch("src.admin_ui.auth.get_redis_connection", return_value=mock_redis):
            with patch.dict(
                os.environ,
                {"ADMIN_UI_RATE_LIMIT": "2", "ADMIN_UI_RATE_LIMIT_WINDOW": "60"},
            ):
                for _ in range(2):
                    resp = self.client.get("/", auth=self.auth, headers=headers)
                    self.assertEqual(resp.status_code, 200)
                resp = self.client.get("/", auth=self.auth, headers=headers)
                self.assertEqual(resp.status_code, 429)

    def test_load_recent_block_events_streaming(self):
        """Ensure _load_recent_block_events reads only the last N lines."""
        tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False)
        try:
            for i in range(10):
                tmp.write(
                    json.dumps(
                        {
                            "timestamp": f"2024-01-01T00:00:0{i}",
                            "ip_address": f"1.1.1.{i}",
                            "reason": "r",
                        }
                    )
                    + "\n"
                )
            tmp.close()
            with patch("src.admin_ui.blocklist.BLOCK_LOG_FILE", tmp.name):
                events = blocklist._load_recent_block_events(limit=5)
            self.assertEqual(len(events), 5)
            self.assertEqual(events[0]["ip"], "1.1.1.5")
            self.assertEqual(events[-1]["ip"], "1.1.1.9")
        finally:
            os.unlink(tmp.name)

    @patch("src.admin_ui.metrics._get_metrics_dict_func")
    def test_metrics_endpoint_success(self, mock_get_metrics_dict):
        """Test the /metrics endpoint with valid, complex Prometheus-formatted data."""
        mock_get_metrics_dict.return_value = {
            'requests_total{method="GET"}': 150.0,
            'requests_total{method="POST"}': 50.0,
            "bots_detected_total": 25.0,
            "active_connections": 10.0,
        }

        with patch("src.admin_ui.metrics.METRICS_TRULY_AVAILABLE", True):
            response = self.client.get(
                "/metrics", auth=self.auth, headers=self._totp_headers()
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['requests_total{method="GET"}'], 150.0)
        self.assertEqual(data["bots_detected_total"], 25.0)

    @patch("src.admin_ui.metrics.METRICS_TRULY_AVAILABLE", False)
    def test_metrics_endpoint_module_unavailable(self):
        """Test the /metrics endpoint when the metrics module is flagged as unavailable."""
        response = self.client.get(
            "/metrics", auth=self.auth, headers=self._totp_headers()
        )
        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data.get("error"), "Metrics module not available")

    @patch(
        "src.admin_ui.metrics._get_metrics_dict_func",
        return_value={"error": "Parsing failed"},
    )
    def test_metrics_endpoint_parsing_error(self, mock_get_metrics_dict):
        """Test the /metrics endpoint when parsing the Prometheus data fails."""
        with patch("src.admin_ui.metrics.METRICS_TRULY_AVAILABLE", True):
            response = self.client.get(
                "/metrics", auth=self.auth, headers=self._totp_headers()
            )

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "Parsing failed")

    @patch("src.admin_ui.blocklist.get_redis_connection")
    def test_get_blocklist_success(self, mock_get_redis):
        """Test successfully retrieving the blocklist from Redis."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.smembers.return_value = {"1.1.1.1", "2.2.2.2"}
        mock_get_redis.return_value = mock_redis_instance

        response = self.client.get(
            "/blocklist", auth=self.auth, headers=self._totp_headers()
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("1.1.1.1", data)
        self.assertIn("2.2.2.2", data)
        self.assertEqual(len(data), 2)

    @patch("src.admin_ui.blocklist.get_redis_connection", return_value=None)
    def test_get_blocklist_redis_unavailable(self, mock_get_redis):
        """Test the /blocklist endpoint when Redis is unavailable."""
        response = self.client.get(
            "/blocklist", auth=self.auth, headers=self._totp_headers()
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "Redis service unavailable"})

    @patch("src.admin_ui.blocklist.get_redis_connection")
    def test_get_blocklist_invalid_response(self, mock_get_redis):
        """Test the /blocklist endpoint handles invalid Redis responses."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.smembers.return_value = "oops"
        mock_get_redis.return_value = mock_redis_instance

        response = self.client.get(
            "/blocklist", auth=self.auth, headers=self._totp_headers()
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "Redis returned invalid data"})

    @patch("src.admin_ui.blocklist.get_redis_connection")
    def test_block_ip_success(self, mock_get_redis):
        """Test manually blocking an IP address."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.sadd.return_value = 1  # Simulate adding a new member
        mock_get_redis.return_value = mock_redis_instance

        response = self.client.post(
            "/block",
            json={"ip": "3.3.3.3"},
            auth=self.auth,
            headers=self._totp_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success", "ip": "3.3.3.3"})
        mock_redis_instance.sadd.assert_called_once_with("default:blocklist", "3.3.3.3")

    @patch("src.admin_ui.blocklist.get_redis_connection")
    def test_unblock_ip_success(self, mock_get_redis):
        """Test manually unblocking an IP address."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.srem.return_value = 1  # Simulate removing a member
        mock_get_redis.return_value = mock_redis_instance

        response = self.client.post(
            "/unblock",
            json={"ip": "1.1.1.1"},
            auth=self.auth,
            headers=self._totp_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success", "ip": "1.1.1.1"})
        mock_redis_instance.srem.assert_called_once_with("default:blocklist", "1.1.1.1")

    @patch("src.admin_ui.blocklist.get_redis_connection")
    def test_block_ip_requires_admin(self, mock_get_redis):
        """Non-admin users receive 403 when attempting to block an IP."""
        os.environ["ADMIN_UI_ROLE"] = "viewer"
        auth.ADMIN_UI_ROLE = "viewer"
        mock_redis_instance = MagicMock()
        mock_redis_instance.sadd.return_value = 1
        mock_get_redis.return_value = mock_redis_instance
        response = self.client.post(
            "/block",
            json={"ip": "4.4.4.4"},
            auth=self.auth,
            headers=self._totp_headers(),
        )
        self.assertEqual(response.status_code, 403)
        os.environ["ADMIN_UI_ROLE"] = "admin"
        auth.ADMIN_UI_ROLE = "admin"

    def test_block_ip_invalid_payload(self):
        """Test the /block endpoint with an invalid payload."""
        response = self.client.post(
            "/block",
            json={"address": "3.3.3.3"},
            auth=self.auth,
            headers=self._totp_headers(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid request, missing ip"})

    def test_2fa_required_and_valid(self):
        """Requests succeed when a valid TOTP code is supplied."""
        secret = "JBSWY3DPEHPK3PXP"
        os.environ["ADMIN_UI_2FA_SECRET"] = secret
        code = pyotp.TOTP(secret).now()
        headers = {"X-2FA-Code": code}
        response = self.client.get("/", auth=self.auth, headers=headers)
        self.assertEqual(response.status_code, 200)
        del os.environ["ADMIN_UI_2FA_SECRET"]

    def test_2fa_missing_code(self):
        """Missing TOTP code results in 401 when 2FA is enabled."""
        secret = "JBSWY3DPEHPK3PXP"
        os.environ["ADMIN_UI_2FA_SECRET"] = secret
        response = self.client.get("/", auth=self.auth)
        self.assertEqual(response.status_code, 401)
        del os.environ["ADMIN_UI_2FA_SECRET"]

    def test_2fa_invalid_code(self):
        """Invalid TOTP code results in 401."""
        secret = "JBSWY3DPEHPK3PXP"
        os.environ["ADMIN_UI_2FA_SECRET"] = secret
        headers = {"X-2FA-Code": "000000"}
        response = self.client.get("/", auth=self.auth, headers=headers)
        self.assertEqual(response.status_code, 401)
        del os.environ["ADMIN_UI_2FA_SECRET"]

    def test_webauthn_token_allows_login(self):
        """A valid WebAuthn token satisfies the 2FA requirement."""
        secret = "JBSWY3DPEHPK3PXP"
        os.environ["ADMIN_UI_2FA_SECRET"] = secret
        token = "tok123"

        class MockRedis:
            def __init__(self):
                self.store = {}

            def set(self, key, value, ex=None):
                self.store[key] = value

            def getdel(self, key):
                return self.store.pop(key, None)

            def get(self, key):
                return self.store.get(key)

            def scan_iter(self, pattern, count=1):
                import fnmatch

                for k in list(self.store.keys()):
                    if fnmatch.fnmatch(k, pattern):
                        yield k

        mock_redis = MockRedis()
        with patch(
            "src.admin_ui.webauthn.get_redis_connection", return_value=mock_redis
        ):
            webauthn._store_webauthn_token(token, "admin", time.time() + 60)
            headers = {"X-2FA-Token": token}
            response = self.client.get("/", auth=self.auth, headers=headers)

            self.assertEqual(response.status_code, 200)
            webauthn._consume_webauthn_token(token)
        del os.environ["ADMIN_UI_2FA_SECRET"]

    def test_webauthn_token_invalid(self):
        """Invalid WebAuthn tokens are rejected."""
        secret = "JBSWY3DPEHPK3PXP"
        os.environ["ADMIN_UI_2FA_SECRET"] = secret

        class MockRedis:
            def __init__(self):
                self.store = {}

            def set(self, key, value, ex=None):
                self.store[key] = value

            def getdel(self, key):
                return self.store.pop(key, None)

            def get(self, key):
                return self.store.get(key)

            def scan_iter(self, pattern, count=1):
                import fnmatch

                for k in list(self.store.keys()):
                    if fnmatch.fnmatch(k, pattern):
                        yield k

        mock_redis = MockRedis()
        with patch(
            "src.admin_ui.webauthn.get_redis_connection", return_value=mock_redis
        ):
            webauthn._store_webauthn_token("good", "admin", time.time() + 60)
            headers = {"X-2FA-Token": "bad"}
            response = self.client.get("/", auth=self.auth, headers=headers)
            self.assertEqual(response.status_code, 401)
            webauthn._consume_webauthn_token("good")
        del os.environ["ADMIN_UI_2FA_SECRET"]

    def test_webauthn_login_begin_invalid_username(self):
        """Login begin rejects missing username."""
        response = self.client.post("/webauthn/login/begin", json={})
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual("Invalid login request", data["detail"])

    def test_webauthn_login_complete_invalid_username(self):
        """Login complete rejects invalid username before processing."""
        payload = {"username": "", "credential": {}}
        response = self.client.post("/webauthn/login/complete", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual("Invalid login request", data["detail"])

    def test_missing_admin_password(self):
        """Service raises an error when ADMIN_UI_PASSWORD_HASH is unset."""
        original_password = os.environ.get("ADMIN_UI_PASSWORD_HASH")
        try:
            del os.environ["ADMIN_UI_PASSWORD_HASH"]
            with self.assertRaises(RuntimeError):
                self.client.get("/", auth=self.auth, headers=self._totp_headers())
        finally:
            if original_password is not None:
                os.environ["ADMIN_UI_PASSWORD_HASH"] = original_password

    @patch("src.admin_ui.metrics._get_metrics_dict_func")
    def test_metrics_websocket_initial_message(self, mock_get_metrics):
        """Ensure the /ws/metrics endpoint streams metrics on connect."""
        mock_get_metrics.return_value = {"active_connections": 5}
        headers = {
            "Authorization": "Basic YWRtaW46dGVzdHBhc3M=",
            **self._totp_headers(),
        }
        with self.client.websocket_connect("/ws/metrics", headers=headers) as websocket:
            data = websocket.receive_json()
        self.assertEqual(data, {"active_connections": 5})
        mock_get_metrics.assert_called()

    @patch("src.admin_ui.metrics.METRICS_TRULY_AVAILABLE", False)
    def test_metrics_websocket_module_unavailable(self):
        """WebSocket should send an error if metrics are unavailable."""
        headers = {
            "Authorization": "Basic YWRtaW46dGVzdHBhc3M=",
            **self._totp_headers(),
        }
        with self.client.websocket_connect("/ws/metrics", headers=headers) as websocket:
            data = websocket.receive_json()
        self.assertEqual(data, {"error": "Metrics module not available"})

    @patch("src.admin_ui.metrics._get_metrics_dict_func")
    @patch("src.admin_ui.blocklist.get_redis_connection")
    @patch("src.admin_ui.blocklist._load_recent_block_events_func")
    def test_block_stats_success(self, mock_load, mock_get_redis, mock_get_metrics):
        """Test the /block_stats endpoint aggregates data correctly."""
        mock_get_metrics.return_value = {
            "bots_detected_high_score_total": 10.0,
            "humans_detected_low_score_total": 5.0,
        }
        mock_redis = MagicMock()
        mock_redis.smembers.return_value = {"4.4.4.4"}
        mock_redis.scan.return_value = (
            0,
            ["blocklist:ip:4.4.4.4", "blocklist:ip:5.5.5.5"],
        )
        mock_get_redis.return_value = mock_redis
        mock_load.return_value = [
            {"ip": "4.4.4.4", "reason": "test", "timestamp": "2025-01-01T00:00:00Z"}
        ]

        response = self.client.get(
            "/block_stats", auth=self.auth, headers=self._totp_headers()
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["blocked_ip_count"], 1)
        self.assertEqual(data["temporary_block_count"], 2)
        self.assertEqual(data["total_bots_detected"], 10.0)
        self.assertEqual(data["total_humans_detected"], 5.0)
        self.assertEqual(len(data["recent_block_events"]), 1)

    @patch("src.admin_ui.metrics._get_metrics_dict_func", side_effect=Exception("fail"))
    @patch("src.admin_ui.blocklist.get_redis_connection", return_value=None)
    @patch("src.admin_ui.blocklist._load_recent_block_events_func", return_value=[])
    def test_block_stats_handles_errors(
        self, mock_load, mock_get_redis, mock_get_metrics
    ):
        """Test /block_stats handles missing data gracefully."""
        response = self.client.get(
            "/block_stats", auth=self.auth, headers=self._totp_headers()
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["blocked_ip_count"], 0)
        self.assertEqual(data["temporary_block_count"], 0)
        self.assertEqual(data["total_bots_detected"], 0)
        self.assertEqual(data["total_humans_detected"], 0)


if __name__ == "__main__":
    unittest.main()
