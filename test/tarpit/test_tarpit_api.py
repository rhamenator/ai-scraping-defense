# test/tarpit/tarpit_api.test.py
import os
import subprocess
import sys
import unittest
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient

os.environ.setdefault("SYSTEM_SEED", "test-seed")
from src.tarpit.tarpit_api import DEFAULT_SYSTEM_SEED, app, sanitize_headers


class TestTarpitAPIComprehensive(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """Set up test client and patch all external dependencies."""
        self.client = TestClient(app)

        self.patches = {
            "log_honeypot_hit": patch("src.tarpit.tarpit_api.log_honeypot_hit"),
            "flag_suspicious_ip": patch("src.tarpit.tarpit_api.flag_suspicious_ip"),
            "generate_dynamic_tarpit_page": patch(
                "src.tarpit.tarpit_api.generate_dynamic_tarpit_page",
                return_value="<html>Mock Tarpit Page</html>",
            ),
            "get_redis_connection": patch("src.tarpit.tarpit_api.get_redis_connection"),
            "ip_get_redis_connection": patch(
                "src.tarpit.ip_flagger.get_redis_connection"
            ),
            "shared_get_redis_connection": patch(
                "src.shared.redis_client.get_redis_connection"
            ),
            "is_ip_flagged": patch("src.tarpit.tarpit_api.is_ip_flagged"),
            "trigger_ip_block": patch("src.tarpit.tarpit_api.trigger_ip_block"),
            "httpx.AsyncClient": patch("src.tarpit.tarpit_api.httpx.AsyncClient"),
            "ENABLE_TARPIT_CATCH_ALL": patch(
                "src.tarpit.tarpit_api.ENABLE_TARPIT_CATCH_ALL", True
            ),
        }
        self.mocks = {name: p.start() for name, p in self.patches.items()}
        self.mocks["is_ip_flagged"].return_value = False

        # Configure mock Redis clients
        self.mock_redis_hops = MagicMock()
        self.mock_redis_blocklist = MagicMock()

        def get_conn_side_effect(db_number=0):
            if db_number == 4:
                return self.mock_redis_hops
            elif db_number == 2:
                return self.mock_redis_blocklist
            else:
                return self.mock_redis_hops

        self.mocks["get_redis_connection"].side_effect = get_conn_side_effect
        self.mocks["shared_get_redis_connection"].side_effect = get_conn_side_effect
        self.mocks["ip_get_redis_connection"].side_effect = get_conn_side_effect
        # Update module-level redis clients created during import
        import src.tarpit.tarpit_api as tarpit_api

        tarpit_api.redis_hops = self.mock_redis_hops
        tarpit_api.redis_blocklist = self.mock_redis_blocklist
        self.mock_redis_hops.exists.return_value = 0

        # Configure mock AsyncClient
        self.async_client_instance = AsyncMock()
        post_mock = AsyncMock()
        post_mock.return_value = MagicMock(status_code=200, text="ok")
        self.async_client_instance.__aenter__.return_value.post = post_mock
        self.mocks["httpx.AsyncClient"].return_value = self.async_client_instance

    def tearDown(self):
        """Stop all patches."""
        for p in self.patches.values():
            p.stop()

    async def test_tarpit_handler_normal_flow(self):
        """Test the standard flow: log, flag, escalate, and serve content."""
        # Mock Redis pipeline for hop check (not exceeding limit)
        mock_pipeline = self.mock_redis_hops.pipeline.return_value
        mock_pipeline.execute.return_value = [10, True]  # Hop count is 10

        response = self.client.get(
            "/tarpit/some/path", headers={"User-Agent": "TestBot"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text.strip(), "<html>Mock Tarpit Page</html>")

        # Verify all actions were taken
        self.mocks["log_honeypot_hit"].assert_called_once()
        self.mocks["flag_suspicious_ip"].assert_called_once()
        self.mocks["generate_dynamic_tarpit_page"].assert_called_once()
        self.mocks["trigger_ip_block"].assert_not_called()

    async def test_tarpit_handler_hop_limit_exceeded(self):
        """Test that the request is blocked and reported if the hop limit is exceeded."""
        mock_pipeline = self.mock_redis_hops.pipeline.return_value
        mock_pipeline.execute.return_value = [
            300,
            True,
        ]  # Hop count exceeds default of 250

        self.mock_redis_hops.exists.return_value = 1
        self.mocks["is_ip_flagged"].return_value = True
        with patch("src.tarpit.tarpit_api.TAR_PIT_MAX_HOPS", 250), patch(
            "src.tarpit.tarpit_api.HOP_LIMIT_ENABLED", True
        ):
            response = self.client.get("/tarpit/blocked/path")

        self.assertEqual(response.status_code, 403)
        self.assertIn("Access Denied", response.text)
        self.mocks["trigger_ip_block"].assert_called_once_with("testclient", ANY)

        # Ensure other actions are NOT taken
        self.mocks["log_honeypot_hit"].assert_not_called()
        self.mocks["generate_dynamic_tarpit_page"].assert_not_called()

    async def test_tarpit_handler_escalation_fails_gracefully(self):
        """Test that the tarpit still serves content even if escalation to the AI service fails."""
        self.async_client_instance.__aenter__.return_value.post.side_effect = (
            httpx.RequestError("Connection failed")
        )
        mock_pipeline = self.mock_redis_hops.pipeline.return_value
        mock_pipeline.execute.return_value = [15, True]

        with self.assertLogs("src.tarpit.tarpit_api", level="ERROR") as cm:
            response = self.client.get("/tarpit/fail/path")
            self.assertIn("Error escalating request", cm.output[0])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text.strip(), "<html>Mock Tarpit Page</html>")
        # All other actions besides escalation should have happened
        self.mocks["log_honeypot_hit"].assert_called_once()
        self.mocks["generate_dynamic_tarpit_page"].assert_called_once()

    def test_health_check_healthy(self):
        """Test the health check endpoint when all dependencies are healthy."""
        self.mock_redis_hops.ping.return_value = True
        self.mock_redis_blocklist.ping.return_value = True

        with patch("src.tarpit.tarpit_api.GENERATOR_AVAILABLE", True):
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["redis_hops_connected"])
        self.assertTrue(data["redis_blocklist_connected"])
        self.assertTrue(data["generator_available"])

    def test_health_check_redis_unhealthy(self):
        """Test the health check when a Redis instance is unavailable."""
        self.mock_redis_hops.ping.return_value = True
        self.mock_redis_blocklist.ping.side_effect = ConnectionError

        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertTrue(data["redis_hops_connected"])
        self.assertFalse(data["redis_blocklist_connected"])

    def test_sanitize_headers_removes_control_chars(self):
        headers = {"X-Test": "va\tlu\ne\rwith\x0bcontrols"}
        result = sanitize_headers(headers)
        self.assertEqual(result["X-Test"], "valuewithcontrols")

    def test_import_fails_with_default_seed(self):
        """Importing with the placeholder seed should raise an error in production."""
        code = (
            "import os\n"
            f"os.environ['SYSTEM_SEED']={repr(DEFAULT_SYSTEM_SEED)}\n"
            "os.environ['ENVIRONMENT']='production'\n"
            "import src.tarpit.tarpit_api\n"
        )
        env = {
            **os.environ,
            "PYTHONPATH": os.getcwd() + os.pathsep + os.environ.get("PYTHONPATH", ""),
        }
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, env=env
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SYSTEM_SEED", result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
