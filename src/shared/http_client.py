"""HTTP client abstraction providing async context-managed HTTP functionality.

This module provides a clean abstraction over httpx.AsyncClient for making HTTP requests
with proper connection lifecycle management, error handling, and helper methods for
common HTTP operations like JSON POST requests.

Key Features:
- Async context manager for proper connection lifecycle
- Configurable timeouts and connection limits
- JSON request/response helpers
- Comprehensive error handling and logging
- Connection pooling and reuse

Usage Example:
    async with AsyncHttpClient(timeout=10.0) as client:
        response = await client.async_post_json(
            "https://api.example.com/webhook",
            {"message": "test"},
            headers={"Content-Type": "application/json"}
        )
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence
from urllib.parse import urlparse

from .ssrf_protection import SSRFProtectionError, validate_url

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    # Create stubs for development environments without httpx

    class httpx:

        class AsyncClient:

            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def post(self, *args, **kwargs):
                raise RuntimeError("httpx not available")

            async def get(self, *args, **kwargs):
                raise RuntimeError("httpx not available")

        class Response:

            def __init__(self):
                self.status_code = 200
                self.content = b"test"
                self.text = "test"

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise httpx.HTTPStatusError("HTTP error", response=self)

        class HTTPError(Exception):
            pass

        class RequestError(HTTPError):
            pass

        class TimeoutException(HTTPError):
            pass

        class HTTPStatusError(HTTPError):

            def __init__(self, message, response=None):
                super().__init__(message)
                self.response = response

        class Limits:

            def __init__(self, *args, **kwargs):
                pass


logger = logging.getLogger(__name__)


@dataclass
class CircuitState:
    failures: int = 0
    opened_until: float = 0.0


_circuit_states: dict[str, CircuitState] = {}


class CircuitBreakerOpenError(RuntimeError):
    """Raised when the circuit breaker is open for a host."""


def _parse_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _parse_float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _parse_statuses(value: str, default: Sequence[int]) -> Sequence[int]:
    if not value:
        return default
    statuses = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            statuses.append(int(item))
        except ValueError:
            continue
    return statuses or default


class AsyncHttpClient:
    """Async context-managed HTTP client abstraction using httpx.AsyncClient.

    Provides a clean interface for making HTTP requests with proper connection
    lifecycle management, configurable timeouts, and helper methods for common
    operations like JSON POST requests.

    Includes built-in SSRF protection to prevent requests to private IPs,
    localhost, and enforce domain allowlists.

    Attributes:
        timeout (float): Default timeout in seconds for HTTP requests
        follow_redirects (bool): Whether to follow HTTP redirects
        verify (bool): Whether to verify SSL certificates
        limits (httpx.Limits): Connection pool limits configuration
        allowed_domains (Optional[Sequence[str]]): Allowlist of permitted domains
        block_private_ips (bool): Whether to block private IP addresses
        require_https (bool): Whether to require HTTPS for all requests
    """

    def __init__(
        self,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        verify: bool = True,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
        allowed_domains: Optional[Sequence[str]] = None,
        block_private_ips: bool = True,
        require_https: bool = False,
        http2: bool | None = None,
        retry_enabled: bool | None = None,
        max_retries: int | None = None,
        retry_backoff_base: float | None = None,
        retry_backoff_max: float | None = None,
        retry_statuses: Optional[Sequence[int]] = None,
        circuit_breaker_enabled: bool | None = None,
        circuit_breaker_threshold: int | None = None,
        circuit_breaker_reset_seconds: float | None = None,
    ):
        """Initialize the HTTP client with configuration.

        Args:
            timeout: Default timeout in seconds for all requests
            follow_redirects: Whether to automatically follow redirects
            verify: Whether to verify SSL certificates
            max_connections: Maximum number of connections in the pool
            max_keepalive_connections: Maximum number of keep-alive connections
            allowed_domains: Optional list of allowed domains for SSRF protection
            block_private_ips: Whether to block requests to private IPs (default: True)
            require_https: Whether to require HTTPS for all requests (default: False)
            http2: Enable HTTP/2 support (default: env HTTP_CLIENT_HTTP2 or false)
        """
        if not HTTPX_AVAILABLE:
            logger.warning(
                "httpx not available. HTTP client functionality will be limited."
            )

        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self.verify = verify
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections
        self.allowed_domains = allowed_domains
        self.block_private_ips = block_private_ips
        self.require_https = require_https
        if http2 is None:
            http2 = os.getenv("HTTP_CLIENT_HTTP2", "false").lower() == "true"
        self.http2 = http2
        if retry_enabled is None:
            retry_enabled = (
                os.getenv("HTTP_CLIENT_RETRY_ENABLED", "false").lower() == "true"
            )
        self.retry_enabled = retry_enabled
        if max_retries is None:
            max_retries = _parse_int_env("HTTP_CLIENT_MAX_RETRIES", 2)
        self.max_retries = max_retries
        if retry_backoff_base is None:
            retry_backoff_base = _parse_float_env(
                "HTTP_CLIENT_BACKOFF_BASE_SECONDS", 0.5
            )
        self.retry_backoff_base = retry_backoff_base
        if retry_backoff_max is None:
            retry_backoff_max = _parse_float_env("HTTP_CLIENT_BACKOFF_MAX_SECONDS", 5.0)
        self.retry_backoff_max = retry_backoff_max
        if retry_statuses is None:
            retry_statuses = _parse_statuses(
                os.getenv("HTTP_CLIENT_RETRY_STATUS", "429,500,502,503,504"),
                [429, 500, 502, 503, 504],
            )
        self.retry_statuses = set(retry_statuses)
        if circuit_breaker_enabled is None:
            circuit_breaker_enabled = (
                os.getenv("HTTP_CLIENT_CIRCUIT_ENABLED", "false").lower() == "true"
            )
        self.circuit_breaker_enabled = circuit_breaker_enabled
        if circuit_breaker_threshold is None:
            circuit_breaker_threshold = _parse_int_env(
                "HTTP_CLIENT_CIRCUIT_FAILURE_THRESHOLD", 5
            )
        self.circuit_breaker_threshold = circuit_breaker_threshold
        if circuit_breaker_reset_seconds is None:
            circuit_breaker_reset_seconds = _parse_float_env(
                "HTTP_CLIENT_CIRCUIT_RESET_SECONDS", 30.0
            )
        self.circuit_breaker_reset_seconds = circuit_breaker_reset_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "AsyncHttpClient":
        """Enter the async context and initialize the HTTP client."""
        if not HTTPX_AVAILABLE:
            logger.error("Cannot create HTTP client: httpx not available")
            return self

        try:
            # Create connection limits for the client
            limits = httpx.Limits(
                max_connections=self.max_connections,
                max_keepalive_connections=self.max_keepalive_connections,
            )

            # Initialize the httpx client with our configuration
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=self.follow_redirects,
                verify=self.verify,
                limits=limits,
                http2=self.http2,
            )

            logger.debug(
                f"HTTP client initialized with timeout={self.timeout}s, "
                f"max_connections={self.max_connections}, "
                f"max_keepalive={self.max_keepalive_connections}, "
                f"http2={'enabled' if self.http2 else 'disabled'}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize HTTP client: {e}")
            self._client = None
            raise

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the async context and properly close the HTTP client."""
        if self._client:
            try:
                await self._client.aclose()
                logger.debug("HTTP client connection closed")
            except Exception as e:
                logger.error(f"Error closing HTTP client: {e}")
            finally:
                self._client = None

    @property
    def is_available(self) -> bool:
        """Check if the HTTP client is available and ready for use."""
        return HTTPX_AVAILABLE and self._client is not None

    def _host_key(self, url: str) -> str:
        parsed = urlparse(url)
        return parsed.netloc or parsed.path

    def _get_circuit_state(self, host: str) -> CircuitState:
        state = _circuit_states.get(host)
        if state is None:
            state = CircuitState()
            _circuit_states[host] = state
        return state

    def _check_circuit(self, host: str) -> None:
        if not self.circuit_breaker_enabled:
            return
        state = self._get_circuit_state(host)
        if state.opened_until and time.time() < state.opened_until:
            raise CircuitBreakerOpenError(f"Circuit breaker open for host {host}")
        if state.opened_until and time.time() >= state.opened_until:
            state.failures = 0
            state.opened_until = 0.0

    def _record_failure(self, host: str) -> None:
        if not self.circuit_breaker_enabled:
            return
        state = self._get_circuit_state(host)
        state.failures += 1
        if state.failures >= self.circuit_breaker_threshold:
            state.opened_until = time.time() + self.circuit_breaker_reset_seconds
            logger.warning(
                "Circuit breaker opened for host %s after %s failures",
                host,
                state.failures,
            )

    def _record_success(self, host: str) -> None:
        if not self.circuit_breaker_enabled:
            return
        state = self._get_circuit_state(host)
        state.failures = 0
        state.opened_until = 0.0

    def _retry_delay(self, attempt: int, response: Optional["httpx.Response"]) -> float:
        retry_after = None
        if response is not None:
            header = response.headers.get("Retry-After")
            if header and header.isdigit():
                retry_after = float(header)
        delay = self.retry_backoff_base * (2 ** max(attempt - 1, 0))
        delay = min(delay, self.retry_backoff_max)
        if retry_after is not None:
            delay = min(delay, retry_after, self.retry_backoff_max)
        return max(delay, 0.0)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> "httpx.Response":
        # Validate URL for SSRF protection first (before checking client availability)
        try:
            validate_url(
                url,
                allowed_domains=self.allowed_domains,
                block_private_ips=self.block_private_ips,
                require_https=self.require_https,
            )
        except SSRFProtectionError as e:
            logger.error(f"SSRF protection blocked {method} request to {url}: {e}")
            raise

        if not self.is_available:
            raise RuntimeError("HTTP client is not available or not initialized")

        request_timeout = timeout if timeout is not None else self.timeout
        retries_allowed = self.max_retries if max_retries is None else max_retries
        if not self.retry_enabled:
            retries_allowed = 0

        host = self._host_key(url)
        attempt = 0

        while True:
            attempt += 1
            self._check_circuit(host)
            try:
                logger.debug(f"Making {method} request to {url}")
                response = await self._client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    json=json_body,
                    timeout=request_timeout,
                )
                logger.debug(
                    f"Received response: {response.status_code} from {url} "
                    f"(Content-Length: {len(response.content)} bytes)"
                )
                if (
                    response.status_code in self.retry_statuses
                    and attempt <= retries_allowed
                ):
                    self._record_failure(host)
                    delay = self._retry_delay(attempt, response)
                    logger.warning(
                        "Retryable status %s from %s (attempt %s/%s). Retrying in %.2fs",
                        response.status_code,
                        url,
                        attempt,
                        retries_allowed,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                self._record_success(host)
                return response
            except (httpx.TimeoutException, httpx.RequestError) as e:
                self._record_failure(host)
                if attempt <= retries_allowed:
                    delay = self._retry_delay(attempt, None)
                    logger.warning(
                        "Request error on %s %s (attempt %s/%s): %s. Retrying in %.2fs",
                        method,
                        url,
                        attempt,
                        retries_allowed,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

    async def async_post_json(
        self,
        url: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> "httpx.Response":
        """Make an async POST request with JSON payload.

        Args:
            url: The URL to send the POST request to
            data: Dictionary to be sent as JSON in the request body
            headers: Optional additional headers to include
            timeout: Optional timeout override for this request

        Returns:
            httpx.Response: The HTTP response object

        Raises:
            RuntimeError: If the HTTP client is not available
            SSRFProtectionError: If the URL fails SSRF validation
            httpx.RequestError: For network-related errors
            httpx.TimeoutException: If the request times out
            httpx.HTTPStatusError: For HTTP status errors (4xx, 5xx)
        """
        # Set default headers for JSON requests
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        return await self._request(
            "POST",
            url,
            headers=request_headers,
            json_body=data,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def async_get(
        self,
        url: str,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> "httpx.Response":
        """Make an async GET request.

        Args:
            url: The URL to send the GET request to
            params: Optional query parameters
            headers: Optional headers to include
            timeout: Optional timeout override for this request

        Returns:
            httpx.Response: The HTTP response object

        Raises:
            RuntimeError: If the HTTP client is not available
            SSRFProtectionError: If the URL fails SSRF validation
            httpx.RequestError: For network-related errors
            httpx.TimeoutException: If the request times out
            httpx.HTTPStatusError: For HTTP status errors (4xx, 5xx)
        """
        return await self._request(
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            max_retries=max_retries,
        )
