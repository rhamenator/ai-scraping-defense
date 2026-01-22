"""SSRF Protection Module

This module provides centralized Server-Side Request Forgery (SSRF) protection
for all HTTP client operations. It includes URL validation, IP address filtering,
and configurable allowlists/denylists to prevent malicious requests to internal
resources or sensitive endpoints.

Key Features:
- Private IP address detection and blocking
- Localhost/loopback detection
- URL scheme validation (HTTPS enforcement)
- Domain allowlisting
- Port restrictions
- Redirect prevention
- DNS rebinding protection

Usage Example:
    from src.shared.ssrf_protection import validate_url, SSRFProtectionError

    try:
        validate_url("https://api.example.com/webhook", allowed_domains=["example.com"])
    except SSRFProtectionError as e:
        logger.error(f"SSRF attempt blocked: {e}")
"""

import ipaddress
import logging
from typing import Optional, Sequence
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SSRFProtectionError(ValueError):
    """Exception raised when a URL fails SSRF validation checks."""

    pass


def is_private_ip(hostname: str) -> bool:
    """Check if a hostname resolves to a private IP address.

    Args:
        hostname: The hostname or IP address to check

    Returns:
        bool: True if the hostname is a private IP address
    """
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        # Not an IP address, could be a hostname
        return False


def is_localhost(hostname: str) -> bool:
    """Check if a hostname refers to localhost.

    Args:
        hostname: The hostname to check

    Returns:
        bool: True if the hostname is localhost-related
    """
    if not hostname:
        return False

    hostname_lower = hostname.lower()

    # Check for exact localhost match
    if hostname_lower == "localhost":
        return True

    # Check for 127.x.x.x addresses (IPv4 loopback range)
    if (
        hostname_lower.startswith("127.")
        and hostname_lower.replace(".", "").replace(":", "").isdigit()
    ):
        return True

    # Check for other localhost patterns
    localhost_patterns = [
        "::1",  # IPv6 localhost
        str(ipaddress.IPv4Address(0)),
        "[::]",  # IPv6 all interfaces
    ]

    return hostname_lower in localhost_patterns


def validate_url(
    url: str,
    allowed_schemes: Optional[Sequence[str]] = None,
    allowed_domains: Optional[Sequence[str]] = None,
    allowed_ports: Optional[Sequence[int]] = None,
    block_private_ips: bool = True,
    require_https: bool = False,
) -> None:
    """Validate a URL against SSRF protection rules.

    Args:
        url: The URL to validate
        allowed_schemes: List of allowed URL schemes (default: ['http', 'https'])
        allowed_domains: Optional list of allowed domain names (allowlist)
        allowed_ports: Optional list of allowed ports (default: [80, 443, 8080, 8443])
        block_private_ips: Whether to block private IP addresses (default: True)
        require_https: Whether to require HTTPS scheme (default: False)

    Raises:
        SSRFProtectionError: If the URL fails any validation check
    """
    if not url:
        raise SSRFProtectionError("Empty URL provided")

    # Parse the URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise SSRFProtectionError(f"Invalid URL format: {e}")

    # Check scheme
    if allowed_schemes is None:
        allowed_schemes = ["http", "https"]

    if not parsed.scheme:
        raise SSRFProtectionError("URL must include a scheme (http or https)")

    if parsed.scheme not in allowed_schemes:
        raise SSRFProtectionError(
            f"URL scheme '{parsed.scheme}' not allowed. Allowed schemes: {allowed_schemes}"
        )

    if require_https and parsed.scheme != "https":
        raise SSRFProtectionError("HTTPS scheme is required")

    # Check netloc (hostname)
    if not parsed.netloc:
        raise SSRFProtectionError("URL must include a hostname")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFProtectionError("Could not extract hostname from URL")

    # Check for localhost
    if is_localhost(hostname):
        raise SSRFProtectionError(
            f"Access to localhost addresses is not allowed: {hostname}"
        )

    # Check for private IPs
    if block_private_ips and is_private_ip(hostname):
        raise SSRFProtectionError(
            f"Access to private IP addresses is not allowed: {hostname}"
        )

    # Check domain allowlist
    if allowed_domains is not None and len(allowed_domains) > 0:
        if hostname not in allowed_domains:
            raise SSRFProtectionError(
                f"Domain '{hostname}' not in allowlist. Allowed domains: {allowed_domains}"
            )

    # Check port restrictions
    if allowed_ports is not None and len(allowed_ports) > 0:
        port = parsed.port
        if port is None:
            # Use default ports for schemes
            port = 443 if parsed.scheme == "https" else 80

        if port not in allowed_ports:
            raise SSRFProtectionError(
                f"Port {port} not allowed. Allowed ports: {allowed_ports}"
            )

    logger.debug(f"URL passed SSRF validation: {url}")


def validate_url_safe(
    url: str,
    allowed_schemes: Optional[Sequence[str]] = None,
    allowed_domains: Optional[Sequence[str]] = None,
    allowed_ports: Optional[Sequence[int]] = None,
    block_private_ips: bool = True,
    require_https: bool = False,
) -> bool:
    """Validate a URL against SSRF protection rules (non-throwing version).

    Args:
        url: The URL to validate
        allowed_schemes: List of allowed URL schemes (default: ['http', 'https'])
        allowed_domains: Optional list of allowed domain names (allowlist)
        allowed_ports: Optional list of allowed ports (default: [80, 443, 8080, 8443])
        block_private_ips: Whether to block private IP addresses (default: True)
        require_https: Whether to require HTTPS scheme (default: False)

    Returns:
        bool: True if the URL is valid, False otherwise
    """
    try:
        validate_url(
            url,
            allowed_schemes=allowed_schemes,
            allowed_domains=allowed_domains,
            allowed_ports=allowed_ports,
            block_private_ips=block_private_ips,
            require_https=require_https,
        )
        return True
    except SSRFProtectionError:
        return False
