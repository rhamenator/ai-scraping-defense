"""Tests for SSRF protection module."""

import unittest

from src.shared.ssrf_protection import (
    SSRFProtectionError,
    is_localhost,
    is_private_ip,
    validate_url,
    validate_url_safe,
)


class TestIsPrivateIP(unittest.TestCase):
    """Test is_private_ip function."""

    def test_private_ipv4_addresses(self):
        """Test that private IPv4 addresses are detected."""
        self.assertTrue(is_private_ip("192.168.1.1"))
        self.assertTrue(is_private_ip("10.0.0.1"))
        self.assertTrue(is_private_ip("172.16.0.1"))
        self.assertTrue(is_private_ip("172.31.255.255"))

    def test_loopback_addresses(self):
        """Test that loopback addresses are detected."""
        self.assertTrue(is_private_ip("127.0.0.1"))
        self.assertTrue(is_private_ip("::1"))

    def test_link_local_addresses(self):
        """Test that link-local addresses are detected."""
        self.assertTrue(is_private_ip("169.254.1.1"))

    def test_public_ip_addresses(self):
        """Test that public IP addresses are not flagged as private."""
        self.assertFalse(is_private_ip("8.8.8.8"))
        self.assertFalse(is_private_ip("1.1.1.1"))
        self.assertFalse(is_private_ip("93.184.216.34"))

    def test_hostname_not_ip(self):
        """Test that hostnames return False (not IP addresses)."""
        self.assertFalse(is_private_ip("example.com"))
        self.assertFalse(is_private_ip("api.example.com"))


class TestIsLocalhost(unittest.TestCase):
    """Test is_localhost function."""

    def test_localhost_variants(self):
        """Test various localhost patterns."""
        self.assertTrue(is_localhost("localhost"))
        self.assertTrue(is_localhost("LOCALHOST"))
        self.assertTrue(is_localhost("LocalHost"))
        self.assertTrue(is_localhost("127.0.0.1"))
        self.assertTrue(is_localhost("127.1.1.1"))
        self.assertTrue(is_localhost("::1"))
        self.assertTrue(is_localhost("0.0.0.0"))  # nosec B104
        self.assertTrue(is_localhost("[::]"))

    def test_non_localhost(self):
        """Test that non-localhost addresses are not flagged."""
        self.assertFalse(is_localhost("example.com"))
        self.assertFalse(is_localhost("192.168.1.1"))
        self.assertFalse(is_localhost("8.8.8.8"))
        self.assertFalse(is_localhost("127example.com"))

    def test_empty_string(self):
        """Test that empty string returns False."""
        self.assertFalse(is_localhost(""))


class TestValidateURL(unittest.TestCase):
    """Test validate_url function."""

    def test_valid_https_url(self):
        """Test that valid HTTPS URLs pass validation."""
        validate_url("https://example.com/path")
        validate_url("https://api.example.com:443/endpoint")

    def test_valid_http_url(self):
        """Test that valid HTTP URLs pass validation."""
        validate_url("http://example.com/path")

    def test_empty_url(self):
        """Test that empty URL raises error."""
        with self.assertRaises(SSRFProtectionError) as ctx:
            validate_url("")
        self.assertIn("Empty URL", str(ctx.exception))

    def test_missing_scheme(self):
        """Test that URL without scheme raises error."""
        with self.assertRaises(SSRFProtectionError) as ctx:
            validate_url("example.com/path")
        self.assertIn("scheme", str(ctx.exception))

    def test_invalid_scheme(self):
        """Test that URLs with invalid schemes are rejected."""
        with self.assertRaises(SSRFProtectionError) as ctx:
            validate_url("ftp://example.com/file")
        self.assertIn("not allowed", str(ctx.exception))

    def test_require_https(self):
        """Test that require_https parameter enforces HTTPS."""
        with self.assertRaises(SSRFProtectionError) as ctx:
            validate_url("http://example.com", require_https=True)
        self.assertIn("HTTPS", str(ctx.exception))

    def test_missing_hostname(self):
        """Test that URL without hostname raises error."""
        with self.assertRaises(SSRFProtectionError) as ctx:
            validate_url("https:///path")
        self.assertIn("hostname", str(ctx.exception))

    def test_localhost_blocked(self):
        """Test that localhost addresses are blocked."""
        with self.assertRaises(SSRFProtectionError) as ctx:
            validate_url("http://localhost/api")
        self.assertIn("localhost", str(ctx.exception))

        with self.assertRaises(SSRFProtectionError) as ctx:
            validate_url("http://127.0.0.1/api")
        self.assertIn("localhost", str(ctx.exception))

    def test_private_ip_blocked(self):
        """Test that private IP addresses are blocked."""
        with self.assertRaises(SSRFProtectionError) as ctx:
            validate_url("http://192.168.1.1/api")
        self.assertIn("private IP", str(ctx.exception))

        with self.assertRaises(SSRFProtectionError) as ctx:
            validate_url("http://10.0.0.1/api")
        self.assertIn("private IP", str(ctx.exception))

    def test_private_ip_allowed(self):
        """Test that private IPs can be allowed with block_private_ips=False."""
        validate_url("http://192.168.1.1/api", block_private_ips=False)

    def test_domain_allowlist(self):
        """Test that domain allowlist is enforced."""
        allowed = ["example.com", "api.example.com"]

        # Allowed domain should pass
        validate_url("https://example.com/path", allowed_domains=allowed)

        # Non-allowed domain should fail
        with self.assertRaises(SSRFProtectionError) as ctx:
            validate_url("https://evil.com/path", allowed_domains=allowed)
        self.assertIn("not in allowlist", str(ctx.exception))

    def test_port_restrictions(self):
        """Test that port restrictions are enforced."""
        allowed_ports = [80, 443]

        # Standard ports should pass
        validate_url("http://example.com/path", allowed_ports=allowed_ports)
        validate_url("https://example.com/path", allowed_ports=allowed_ports)

        # Non-standard port should fail
        with self.assertRaises(SSRFProtectionError) as ctx:
            validate_url("http://example.com:8080/path", allowed_ports=allowed_ports)
        self.assertIn("Port", str(ctx.exception))

    def test_allowed_schemes(self):
        """Test that custom allowed schemes work."""
        validate_url("ftp://example.com/file", allowed_schemes=["ftp"])

        with self.assertRaises(SSRFProtectionError):
            validate_url("http://example.com", allowed_schemes=["ftp"])


class TestValidateURLSafe(unittest.TestCase):
    """Test validate_url_safe function (non-throwing version)."""

    def test_valid_url_returns_true(self):
        """Test that valid URLs return True."""
        self.assertTrue(validate_url_safe("https://example.com/path"))
        self.assertTrue(validate_url_safe("http://example.com/path"))

    def test_invalid_url_returns_false(self):
        """Test that invalid URLs return False."""
        self.assertFalse(validate_url_safe(""))
        self.assertFalse(validate_url_safe("http://localhost/api"))
        self.assertFalse(validate_url_safe("http://192.168.1.1/api"))
        self.assertFalse(validate_url_safe("ftp://example.com/file"))

    def test_domain_allowlist(self):
        """Test that domain allowlist works with safe version."""
        allowed = ["example.com"]

        self.assertTrue(
            validate_url_safe("https://example.com/path", allowed_domains=allowed)
        )
        self.assertFalse(
            validate_url_safe("https://evil.com/path", allowed_domains=allowed)
        )

    def test_require_https(self):
        """Test that require_https works with safe version."""
        self.assertTrue(validate_url_safe("https://example.com", require_https=True))
        self.assertFalse(validate_url_safe("http://example.com", require_https=True))


if __name__ == "__main__":
    unittest.main()
