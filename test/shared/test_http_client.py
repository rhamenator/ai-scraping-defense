"""Tests for HTTP client with SSRF protection."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.shared.http_client import AsyncHttpClient
from src.shared.ssrf_protection import SSRFProtectionError


class TestAsyncHttpClientSSRFProtection(unittest.IsolatedAsyncioTestCase):
    """Test SSRF protection in AsyncHttpClient."""

    async def test_post_json_blocks_localhost(self):
        """Test that POST requests to localhost are blocked."""
        async with AsyncHttpClient() as client:
            with self.assertRaises(SSRFProtectionError) as ctx:
                await client.async_post_json("http://localhost:8080/api", {"test": "data"})
            self.assertIn("localhost", str(ctx.exception))

    async def test_post_json_blocks_private_ip(self):
        """Test that POST requests to private IPs are blocked."""
        async with AsyncHttpClient() as client:
            with self.assertRaises(SSRFProtectionError) as ctx:
                await client.async_post_json("http://192.168.1.1/api", {"test": "data"})
            self.assertIn("private IP", str(ctx.exception))

    async def test_get_blocks_localhost(self):
        """Test that GET requests to localhost are blocked."""
        async with AsyncHttpClient() as client:
            with self.assertRaises(SSRFProtectionError) as ctx:
                await client.async_get("http://localhost:8080/api")
            self.assertIn("localhost", str(ctx.exception))

    async def test_get_blocks_private_ip(self):
        """Test that GET requests to private IPs are blocked."""
        async with AsyncHttpClient() as client:
            with self.assertRaises(SSRFProtectionError) as ctx:
                await client.async_get("http://10.0.0.1/api")
            self.assertIn("private IP", str(ctx.exception))

    async def test_private_ips_allowed_with_flag(self):
        """Test that private IPs can be allowed with block_private_ips=False."""
        with patch("src.shared.http_client.HTTPX_AVAILABLE", True):
            with patch("src.shared.http_client.httpx.AsyncClient") as mock_client_class:
                with patch("src.shared.http_client.httpx.Limits"):
                    mock_client = AsyncMock()
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.content = b"test"
                    mock_client.get.return_value = mock_response
                    mock_client_class.return_value = mock_client

                    async with AsyncHttpClient(block_private_ips=False) as client:
                        # Should not raise SSRFProtectionError
                        await client.async_get("http://192.168.1.1/api")

    async def test_domain_allowlist_enforced(self):
        """Test that domain allowlist is enforced."""
        with patch("src.shared.http_client.HTTPX_AVAILABLE", True):
            with patch("src.shared.http_client.httpx.AsyncClient") as mock_client_class:
                with patch("src.shared.http_client.httpx.Limits"):
                    mock_client = AsyncMock()
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.content = b"test"
                    mock_client.get.return_value = mock_response
                    mock_client_class.return_value = mock_client

                    async with AsyncHttpClient(allowed_domains=["example.com"]) as client:
                        # This should pass SSRF validation
                        await client.async_get("http://example.com/api")

                        # Non-allowed domain should fail
                        with self.assertRaises(SSRFProtectionError) as ctx:
                            await client.async_get("http://evil.com/api")
                        self.assertIn("not in allowlist", str(ctx.exception))

    async def test_require_https_enforced(self):
        """Test that require_https flag is enforced."""
        with patch("src.shared.http_client.HTTPX_AVAILABLE", True):
            with patch("src.shared.http_client.httpx.AsyncClient") as mock_client_class:
                with patch("src.shared.http_client.httpx.Limits"):
                    mock_client = AsyncMock()
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.content = b"test"
                    mock_client.get.return_value = mock_response
                    mock_client_class.return_value = mock_client

                    async with AsyncHttpClient(require_https=True) as client:
                        # HTTP should fail
                        with self.assertRaises(SSRFProtectionError) as ctx:
                            await client.async_get("http://example.com/api")
                        self.assertIn("HTTPS", str(ctx.exception))

                        # HTTPS should work
                        await client.async_get("https://example.com/api")

    async def test_valid_public_url_works(self):
        """Test that valid public URLs work normally."""
        with patch("src.shared.http_client.HTTPX_AVAILABLE", True):
            with patch("src.shared.http_client.httpx.AsyncClient") as mock_client_class:
                with patch("src.shared.http_client.httpx.Limits"):
                    mock_client = AsyncMock()
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.content = b"success"
                    mock_client.post.return_value = mock_response
                    mock_client_class.return_value = mock_client

                    async with AsyncHttpClient() as client:
                        response = await client.async_post_json(
                            "https://api.example.com/webhook",
                            {"test": "data"}
                        )
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.content, b"success")


if __name__ == "__main__":
    unittest.main()
