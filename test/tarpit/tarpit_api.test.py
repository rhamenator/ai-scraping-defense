# test/tarpit/tarpit_api.test.py
import unittest
from unittest.mock import patch, MagicMock, AsyncMock, ANY # Ensure ANY is imported
import os
import datetime
import json
import asyncio 
import httpx # Added for httpx.RequestError

from fastapi.testclient import TestClient

from tarpit import tarpit_api 
from tarpit.tarpit_api import app 

# Helper to reset module-level states
def reset_tarpit_api_module_state():
    tarpit_api.HONEYPOT_LOGGING_AVAILABLE = True 
    tarpit_api.GENERATOR_AVAILABLE = True       
    tarpit_api.FLAGGING_AVAILABLE = True        
    # Ensure TAR_PIT_MAX_HOPS is read from the module, not a local variable if it's changed by tests
    tarpit_api.HOP_LIMIT_ENABLED = getattr(tarpit_api, 'TAR_PIT_MAX_HOPS', 0) > 0
    tarpit_api.redis_hops = None
    tarpit_api.redis_blocklist = None
    # Reset other constants if they are modified by tests via patching module attributes
    # For example, if a test patches tarpit_api.ESCALATION_ENDPOINT, it should be reset here
    # or managed via @patch.object for specific tests.

class TestTarpitAPIHelpers(unittest.IsolatedAsyncioTestCase):

    async def test_slow_stream_content(self):
        content = "Line 1\nLine 2\nLine 3"
        with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
            streamed_parts = []
            # Test the actual async generator
            async for part in tarpit_api.slow_stream_content(content):
                streamed_parts.append(part)
            
            self.assertEqual(len(streamed_parts), 3)
            self.assertEqual("".join(streamed_parts), "Line 1\nLine 2\nLine 3\n")
            self.assertGreaterEqual(mock_sleep.call_count, 2)


    @patch("tarpit.tarpit_api.logger")
    def test_trigger_ip_block_success(self, mock_logger):
        mock_redis_blocklist_client = MagicMock()
        mock_redis_blocklist_client.set.return_value = True

        with patch("tarpit.tarpit_api.redis_blocklist", mock_redis_blocklist_client):
            result = tarpit_api.trigger_ip_block("1.2.3.4", "Test Reason")
            self.assertTrue(result)
            mock_redis_blocklist_client.set.assert_called_once_with(
                "blocklist:1.2.3.4", # SUT uses "blocklist:" + ip
                "Test Reason",
                ex=tarpit_api.BLOCKLIST_TTL_SECONDS
            )
            mock_logger.warning.assert_called_once()

    # ... (other helper tests remain the same as in updated_tarpit_api_test_py) ...
    @patch("tarpit.tarpit_api.logger")
    def test_trigger_ip_block_redis_unavailable(self, mock_logger):
        with patch("tarpit.tarpit_api.redis_blocklist", None):
            result = tarpit_api.trigger_ip_block("1.2.3.4", "Test Reason")
            self.assertFalse(result)
            mock_logger.error.assert_called_with("Cannot block IP 1.2.3.4, Redis blocklist connection unavailable.")

    @patch("tarpit.tarpit_api.logger")
    def test_trigger_ip_block_redis_set_fails(self, mock_logger):
        mock_redis_blocklist_client = MagicMock()
        mock_redis_blocklist_client.set.return_value = False 

        with patch("tarpit.tarpit_api.redis_blocklist", mock_redis_blocklist_client):
            result = tarpit_api.trigger_ip_block("1.2.3.4", "Test Reason")
            self.assertFalse(result)
            mock_logger.error.assert_called_with("Failed to set blocklist key for IP 1.2.3.4 in Redis.")

    @patch("tarpit.tarpit_api.logger")
    def test_trigger_ip_block_redis_error(self, mock_logger):
        mock_redis_blocklist_client = MagicMock()
        mock_redis_blocklist_client.set.side_effect = tarpit_api.RedisError("Connection error")

        with patch("tarpit.tarpit_api.redis_blocklist", mock_redis_blocklist_client):
            result = tarpit_api.trigger_ip_block("1.2.3.4", "Test Reason")
            self.assertFalse(result)
            mock_logger.error.assert_called_with("Redis error while trying to block IP 1.2.3.4: Connection error")


class TestTarpitAPIEndpoints(unittest.TestCase):

    def setUp(self):
        reset_tarpit_api_module_state()
        self.client = TestClient(app)

        self.mock_log_honeypot_patcher = patch("tarpit.tarpit_api.log_honeypot_hit")
        self.mock_log_honeypot = self.mock_log_honeypot_patcher.start()

        self.mock_flag_ip_patcher = patch("tarpit.tarpit_api.flag_suspicious_ip", return_value=True)
        self.mock_flag_ip = self.mock_flag_ip_patcher.start()

        self.mock_generate_page_patcher = patch("tarpit.tarpit_api.generate_dynamic_tarpit_page", return_value="<html>Mocked Page Content</html>")
        self.mock_generate_page = self.mock_generate_page_patcher.start()
        
        self.mock_httpx_client_patcher = patch("tarpit.tarpit_api.httpx.AsyncClient")
        self.mock_httpx_client_constructor = self.mock_httpx_client_patcher.start()
        self.mock_async_client_instance = AsyncMock() 
        self.mock_httpx_client_constructor.return_value = self.mock_async_client_instance
        self.mock_async_client_instance.__aenter__.return_value.post = AsyncMock() 
        
        self.mock_redis_hops_patcher = patch("tarpit.tarpit_api.redis_hops")
        self.mock_redis_hops = self.mock_redis_hops_patcher.start()
        
        self.mock_trigger_block_patcher = patch("tarpit.tarpit_api.trigger_ip_block")
        self.mock_trigger_block = self.mock_trigger_block_patcher.start()

        if self.mock_redis_hops: 
            self.mock_redis_pipeline = MagicMock()
            self.mock_redis_hops.pipeline.return_value = self.mock_redis_pipeline
            self.mock_redis_pipeline.execute.return_value = [1, True] 

    def tearDown(self):
        self.mock_log_honeypot_patcher.stop()
        self.mock_flag_ip_patcher.stop()
        self.mock_generate_page_patcher.stop()
        self.mock_httpx_client_patcher.stop()
        self.mock_redis_hops_patcher.stop()
        self.mock_trigger_block_patcher.stop()

    def test_root_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "AntiScrape Tarpit API"})

    def test_health_check_all_ok(self):
        with patch("tarpit.tarpit_api.GENERATOR_AVAILABLE", True), \
             patch("tarpit.tarpit_api.redis_hops") as mock_rh, \
             patch("tarpit.tarpit_api.redis_blocklist") as mock_rb:
            mock_rh.ping.return_value = True
            mock_rb.ping.return_value = True
            
            response = self.client.get("/health")
            self.assertEqual(response.status_code, 200)
            # Ensure TAR_PIT_MAX_HOPS is accessed from the module for consistency
            hop_limit_enabled = getattr(tarpit_api, 'TAR_PIT_MAX_HOPS', 0) > 0
            max_hops_config = getattr(tarpit_api, 'TAR_PIT_MAX_HOPS', 0) if hop_limit_enabled else "disabled"
            
            self.assertEqual(response.json(), {
                "status": "ok",
                "generator_available": True,
                "postgres_connected": True, 
                "redis_hops_connected": True,
                "redis_blocklist_connected": True,
                "hop_limit_enabled": hop_limit_enabled,
                "max_hops_config": max_hops_config
            })

    # --- Tests for /tarpit/{path:path} ---
    @patch("tarpit.tarpit_api.HOP_LIMIT_ENABLED", True)
    def test_tarpit_handler_hop_limit_exceeded(self):
        # Ensure TAR_PIT_MAX_HOPS is a positive value for this test
        with patch.object(tarpit_api, 'TAR_PIT_MAX_HOPS', 5): # Example limit
            self.mock_redis_pipeline.execute.return_value = [tarpit_api.TAR_PIT_MAX_HOPS + 1, True]
            self.mock_trigger_block.return_value = True 

            response = self.client.get("/tarpit/some/path")
            
            self.assertEqual(response.status_code, 403)
            self.assertIn("Access Denied", response.text)
            self.mock_redis_hops.pipeline.assert_called_once()
            # Use ANY from unittest.mock for the reason string
            self.mock_trigger_block.assert_called_once_with("testclient", ANY) 
            self.mock_log_honeypot.assert_not_called()

    @patch("tarpit.tarpit_api.HOP_LIMIT_ENABLED", True)
    @patch("tarpit.tarpit_api.slow_stream_content") # Patch the SUT's slow_stream_content
    async def test_tarpit_handler_normal_flow(self, mock_slow_stream_sut): # Test method must be async
        self.mock_redis_pipeline.execute.return_value = [10, True] 
        
        # Define a simple async generator to be the return value of the mock
        async def dummy_async_gen(*args, **kwargs):
            yield "<html>Mocked Page"
            yield " Content</html>"
        
        mock_slow_stream_sut.return_value = dummy_async_gen() # Assign the generator instance

        response = self.client.get("/tarpit/another/path") # TestClient handles async endpoint
        
        self.assertEqual(response.status_code, 200)
        # StreamingResponse content needs to be consumed carefully in tests
        # For simplicity, we check if the mocked functions were called.
        # If you need to check streamed content:
        # streamed_content = b""
        # for chunk in response.iter_bytes():
        # streamed_content += chunk
        # self.assertIn(b"Mocked Page Content", streamed_content)
        
        self.mock_log_honeypot.assert_called_once()
        self.mock_flag_ip.assert_called_once_with("testclient")
        self.mock_async_client_instance.__aenter__.return_value.post.assert_called_once()
        self.mock_generate_page.assert_called_once()
        # Check that the SUT's slow_stream_content was called with the generated page
        mock_slow_stream_sut.assert_called_once_with("<html>Mocked Page Content</html>")
        self.mock_trigger_block.assert_not_called()

    @patch("tarpit.tarpit_api.HOP_LIMIT_ENABLED", False)
    @patch("tarpit.tarpit_api.GENERATOR_AVAILABLE", False)
    @patch("tarpit.tarpit_api.slow_stream_content")
    async def test_tarpit_handler_generator_unavailable(self, mock_slow_stream_sut):
        async def dummy_fallback_gen(*args, **kwargs):
            yield "fallback"
            yield " HTML"
        mock_slow_stream_sut.return_value = dummy_fallback_gen()

        response = self.client.get("/tarpit/path")
        self.assertEqual(response.status_code, 200)
        self.mock_generate_page.assert_not_called()
        expected_fallback_content = """<!DOCTYPE html>
<html><head><title>Loading Resource...</title><meta name="robots" content="noindex, nofollow"></head>
<body><h1>Please wait</h1><p>Your content is loading slowly...</p><progress></progress>
</body></html>"""
        mock_slow_stream_sut.assert_called_once_with(expected_fallback_content)

    @patch("tarpit.tarpit_api.httpx.AsyncClient") # Re-patch AsyncClient for this specific test
    @patch.object(tarpit_api.logger, "error")
    @patch("tarpit.tarpit_api.slow_stream_content")
    async def test_tarpit_handler_escalation_failure(self, mock_slow_stream_sut, mock_logger_error, MockHttpxAsyncClient):
        # Setup mock for httpx client post to raise an error
        mock_async_client_instance_local = AsyncMock()
        mock_async_client_instance_local.__aenter__.return_value.post = AsyncMock(side_effect=httpx.RequestError("Escalation failed"))
        MockHttpxAsyncClient.return_value = mock_async_client_instance_local
        
        async def dummy_content_gen(*args, **kwargs): yield "content"
        mock_slow_stream_sut.return_value = dummy_content_gen()
        if self.mock_redis_hops: # Ensure redis_hops is mocked
             self.mock_redis_pipeline.execute.return_value = [1, True]

        response = self.client.get("/tarpit/escalation_fail_path")
        self.assertEqual(response.status_code, 200)
        
        self.assertTrue(mock_logger_error.called)
        found_log = any("Error escalating request" in call_args[0][0] for call_args in mock_logger_error.call_args_list)
        self.assertTrue(found_log, "Escalation error not logged as expected.")

if __name__ == '__main__':
    unittest.main()
