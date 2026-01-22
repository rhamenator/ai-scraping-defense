# test/ai_webhook/test_ai_webhook.py
import asyncio
import hashlib
import hmac
import json
import os
import secrets
import unittest
from importlib import reload
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.ai_service import blocklist, community_reporting
from src.ai_service import main as ai_webhook
from src.shared.config import Config


class TestAIWebhookComprehensive(unittest.TestCase):

    def setUp(self):
        """Set up the FastAPI test client and patch dependencies."""
        self.secret = secrets.token_urlsafe(16)
        reload(ai_webhook)
        self.client = TestClient(ai_webhook.app)
        ai_webhook._request_counts.clear()
        self.mock_redis_client = MagicMock()
        ai_webhook.app.dependency_overrides[ai_webhook.get_redis_blocklist] = (
            lambda: self.mock_redis_client
        )
        ai_webhook.app.dependency_overrides[ai_webhook.get_config] = lambda: Config(
            WEBHOOK_SHARED_SECRET=self.secret
        )

    def tearDown(self):
        """Stop all patches."""
        patch.stopall()
        ai_webhook.app.dependency_overrides.clear()

    def _post(self, payload, headers=None):
        body = json.dumps(payload).encode("utf-8")
        sig = hmac.new(self.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        hdrs = {"X-Signature": sig, "Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        return self.client.post("/webhook", content=body, headers=hdrs)

    def test_webhook_receiver_block_ip_success(self):
        """Test a successful 'block_ip' action."""
        payload = {
            "action": "block_ip",
            "ip": "10.0.0.1",
            "reason": "High bot score",
            "source": "escalation-engine",
        }
        self.mock_redis_client.sadd.return_value = 1
        response = self._post(payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "success", "message": "IP 10.0.0.1 added to blocklist."},
        )
        self.mock_redis_client.sadd.assert_called_once_with(
            "default:blocklist", "10.0.0.1"
        )

    def test_webhook_receiver_allow_ip_success(self):
        """Test a successful 'allow_ip' action."""
        payload = {"action": "allow_ip", "ip": "20.0.0.2"}
        self.mock_redis_client.srem.return_value = 1
        response = self._post(payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "success", "message": "IP 20.0.0.2 removed from blocklist."},
        )
        self.mock_redis_client.srem.assert_called_once_with(
            "default:blocklist", "20.0.0.2"
        )

    def test_webhook_receiver_flag_ip_success(self):
        """Test a successful 'flag_ip' action."""
        payload = {
            "action": "flag_ip",
            "ip": "30.0.0.3",
            "reason": "Suspicious activity",
        }
        self.mock_redis_client.set.return_value = True
        response = self._post(payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"status": "success", "message": "IP 30.0.0.3 flagged."}
        )
        # The key name is defined inside the ai_webhook script
        self.mock_redis_client.set.assert_called_once_with(
            "default:ip_flag:30.0.0.3", "Suspicious activity"
        )

    def test_webhook_receiver_unflag_ip_success(self):
        """Test a successful 'unflag_ip' action."""
        payload = {"action": "unflag_ip", "ip": "40.0.0.4"}
        self.mock_redis_client.delete.return_value = 1
        response = self._post(payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"status": "success", "message": "IP 40.0.0.4 unflagged."}
        )
        self.mock_redis_client.delete.assert_called_once_with(
            "default:ip_flag:40.0.0.4"
        )

    def test_webhook_receiver_invalid_ip(self):
        """Test that an invalid IP returns a 400 error and does not touch Redis."""
        invalid_ip = "999.999.999.999"
        actions = [
            ("block_ip", self.mock_redis_client.sadd, {}),
            ("allow_ip", self.mock_redis_client.srem, {}),
            ("flag_ip", self.mock_redis_client.set, {"reason": "x"}),
            ("unflag_ip", self.mock_redis_client.delete, {}),
        ]

        for action, redis_mock, extra in actions:
            with self.subTest(action=action):
                payload = {"action": action, "ip": invalid_ip, **extra}
                response = self._post(payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["detail"], "Invalid payload")
                redis_mock.assert_not_called()
                redis_mock.reset_mock()

    def test_add_ip_to_blocklist_rejects_invalid_ip(self):
        """add_ip_to_blocklist should return False and not touch Redis for invalid IPs."""
        blocklist.BLOCKLISTING_ENABLED = True
        result = blocklist.add_ip_to_blocklist(
            "999.999.999.999", "bad", event_details=None
        )
        self.assertFalse(result)
        self.mock_redis_client.exists.assert_not_called()
        self.mock_redis_client.setex.assert_not_called()

    def test_webhook_receiver_invalid_action(self):
        """Test that an unsupported action returns a 400 error."""
        payload = {"action": "reboot_server", "ip": "1.2.3.4"}
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Invalid payload")

    def test_webhook_receiver_payload_missing_ip(self):
        """Test that a payload missing the 'ip' field returns a 400 error."""
        payload = {"action": "block_ip", "reason": "No IP here."}
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Invalid payload")

    def test_webhook_receiver_missing_signature(self):
        """Request without the signature should be unauthorized."""
        payload = {"action": "block_ip", "ip": "1.2.3.4"}
        body = json.dumps(payload).encode("utf-8")
        response = self.client.post(
            "/webhook",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Unauthorized")

    def test_webhook_receiver_invalid_signature(self):
        """Request with an incorrect signature should be unauthorized."""
        payload = {"action": "block_ip", "ip": "1.2.3.4"}
        body = json.dumps(payload).encode("utf-8")
        wrong_sig = hmac.new(b"wrong", body, hashlib.sha256).hexdigest()
        response = self.client.post(
            "/webhook",
            content=body,
            headers={
                "X-Signature": wrong_sig,
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Unauthorized")

    def test_webhook_receiver_redis_unavailable(self):
        """Test that a 503 error is returned if the Redis connection fails."""
        ai_webhook.app.dependency_overrides[ai_webhook.get_redis_blocklist] = (
            lambda: None
        )
        payload = {"action": "block_ip", "ip": "1.2.3.4"}
        response = self._post(payload)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Redis service unavailable")

    @patch("src.ai_service.main.logger.error")
    def test_webhook_receiver_redis_command_fails(self, mock_logger_error):
        """Test that a 500 error is returned if a Redis command fails."""
        self.mock_redis_client.sadd.side_effect = Exception("Redis command failed")
        payload = {"action": "block_ip", "ip": "1.2.3.4"}
        response = self._post(payload)

        self.assertEqual(response.status_code, 500)
        self.assertIn("Failed to execute action", response.json()["detail"])
        mock_logger_error.assert_called_once()

    def test_health_check_healthy(self):
        """Test the health check endpoint when Redis is connected."""
        self.mock_redis_client.ping.return_value = True
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "redis_connected": True})

    def test_health_check_unhealthy(self):
        """Test the health check endpoint when Redis is not connected."""
        ai_webhook.app.dependency_overrides[ai_webhook.get_redis_blocklist] = (
            lambda: None
        )
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "error", "redis_connected": False})


class TestCommunityReportingTimeout(unittest.IsolatedAsyncioTestCase):
    async def test_report_ip_to_community_json_timeout(self):
        community_reporting.ENABLE_COMMUNITY_REPORTING = True
        community_reporting.COMMUNITY_BLOCKLIST_REPORT_URL = "http://example.com/report"
        community_reporting.COMMUNITY_BLOCKLIST_API_KEY = "key"

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        async def slow_to_thread(func, *args, **kwargs):
            await asyncio.sleep(1)

        with patch(
            "src.ai_service.community_reporting.httpx.AsyncClient",
            return_value=mock_client,
        ), patch(
            "src.ai_service.community_reporting.asyncio.to_thread",
            side_effect=slow_to_thread,
        ), patch(
            "src.ai_service.community_reporting.increment_counter_metric"
        ) as mock_metric, patch(
            "src.ai_service.community_reporting.logger.error"
        ) as mock_log:
            original_timeout = community_reporting.COMMUNITY_BLOCKLIST_REPORT_TIMEOUT
            community_reporting.COMMUNITY_BLOCKLIST_REPORT_TIMEOUT = 0.01
            result = await community_reporting.report_ip_to_community(
                "1.2.3.4", "reason", {}
            )
            community_reporting.COMMUNITY_BLOCKLIST_REPORT_TIMEOUT = original_timeout

        self.assertFalse(result)
        mock_metric.assert_any_call(
            community_reporting.COMMUNITY_REPORTS_ERRORS_TIMEOUT
        )
        mock_log.assert_called()


if __name__ == "__main__":
    unittest.main()
