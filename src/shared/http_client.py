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
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence
from urllib.parse import urljoin, urlparse

from .ssrf_protection import SSRFProtectionError, validate_url
from .validated_transport import ValidatedTransport

# Headers that carry a credential: dropped when a redirect leaves the origin they were meant for.
_CREDENTIAL_HEADER = re.compile(r"(authorization|cookie|api[-_]?key|token|secret|auth)", re.IGNORECASE)

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
        follow_redirects: bool = False,
        max_redirects: int | None = None,
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
        if max_redirects is None:
            max_redirects = _parse_int_env("HTTP_CLIENT_MAX_REDIRECTS", 5)
        self.max_redirects = max(0, max_redirects)
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
            # Redirects are never followed by httpx itself: when enabled they are followed here, one validated hop at a
            # time. With private-address blocking on, connections go through a transport that resolves, checks and
            # connects in one step (#1905).
            transport = (
                ValidatedTransport(verify=self.verify, http2=self.http2, limits=limits)
                if self.block_private_ips
                else None
            )
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=False,
                verify=self.verify,
                limits=limits,
                http2=self.http2,
                transport=transport,
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

    def _validate_destination(self, method: str, url: str) -> None:
        """Early check of a URL (scheme, host rules, allowlist, resolved addresses) with a clear error."""
        try:
            validate_url(
                url,
                allowed_domains=self.allowed_domains,
                block_private_ips=self.block_private_ips,
                require_https=self.require_https,
                resolve_dns=self.block_private_ips,
            )
        except SSRFProtectionError as e:
            logger.error(f"SSRF protection blocked {method} request to {url}: {e}")
            raise

    @staticmethod
    def _origin(url: str) -> tuple[str, str, int]:
        parsed = urlparse(url)
        default = 443 if parsed.scheme == "https" else 80
        return (parsed.scheme, (parsed.hostname or "").lower(), parsed.port or default)

    @staticmethod
    def _without_credentials(headers: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """Headers for a different origin: anything that looks like a credential is dropped."""
        if not headers:
            return headers
        return {k: v for k, v in headers.items() if not _CREDENTIAL_HEADER.search(k)}

    @staticmethod
    def _redirect_request(status: int, method: str, body: Any, headers: Optional[Dict[str, str]]):
        """Method, body and headers for the request that follows a redirect with ``status``."""
        if status == 303 or (status in (301, 302) and method == "POST"):
            kept = {k: v for k, v in (headers or {}).items() if k.lower() != "content-type"}
            return "GET", None, kept
        return method, body, headers

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
        self._validate_destination(method, url)

        if not self.is_available:
            raise RuntimeError("HTTP client is not available or not initialized")

        retries_allowed = self.max_retries if max_retries is None else max_retries
        if not self.retry_enabled:
            retries_allowed = 0

        first = {
            "method": method,
            "url": url,
            "params": params,
            "headers": headers,
            "json_body": json_body,
            "request_timeout": timeout if timeout is not None else self.timeout,
        }
        return await self._follow(first, retries_allowed)

    async def _follow(self, current: Dict[str, Any], retries_allowed: int) -> "httpx.Response":
        """Send ``current`` and, when redirects are enabled, each validated hop after it, up to ``max_redirects``."""
        redirects_left = self.max_redirects
        while True:
            response = await self._send_with_retries(current, retries_allowed)
            location = response.headers.get("location")
            if not (self.follow_redirects and response.is_redirect and location):
                return response
            if redirects_left <= 0:
                raise httpx.TooManyRedirects(
                    f"Exceeded {self.max_redirects} redirects", request=response.request
                )
            redirects_left -= 1
            current = self._next_hop(current, response, location)

    def _next_hop(self, current: Dict[str, Any], response: "httpx.Response", location: str) -> Dict[str, Any]:
        """The request to send after a redirect, validated exactly like the first one (#1905)."""
        next_url = urljoin(current["url"], location)
        self._validate_destination(current["method"], next_url)
        if urlparse(current["url"]).scheme == "https" and urlparse(next_url).scheme != "https":
            raise SSRFProtectionError("Refusing a redirect from HTTPS to HTTP")
        headers = current["headers"]
        if self._origin(current["url"]) != self._origin(next_url):
            headers = self._without_credentials(headers)
        method, body, headers = self._redirect_request(
            response.status_code, current["method"], current["json_body"], headers
        )
        return {
            **current,
            "method": method,
            "url": next_url,
            "params": None,
            "headers": headers,
            "json_body": body,
        }

    async def _send_once(self, request: Dict[str, Any]) -> "httpx.Response":
        logger.debug(f"Making {request['method']} request to {request['url']}")
        response = await self._client.request(
            request["method"],
            request["url"],
            params=request["params"],
            headers=request["headers"],
            json=request["json_body"],
            timeout=request["request_timeout"],
        )
        logger.debug(
            f"Received response: {response.status_code} from {request['url']} "
            f"(Content-Length: {len(response.content)} bytes)"
        )
        return response

    async def _back_off(
        self, attempt: int, retries_allowed: int, request: Dict[str, Any], response: Optional["httpx.Response"], error: object
    ) -> None:
        delay = self._retry_delay(attempt, response)
        logger.warning(
            "Retrying %s %s after %s (attempt %s/%s) in %.2fs",
            request["method"],
            request["url"],
            f"status {response.status_code}" if response is not None else f"error: {error}",
            attempt,
            retries_allowed,
            delay,
        )
        await asyncio.sleep(delay)

    async def _send_with_retries(self, request: Dict[str, Any], retries_allowed: int) -> "httpx.Response":
        """One hop with the configured retries. The connection check happens in the transport, on every attempt."""
        host = self._host_key(request["url"])
        attempt = 0
        while True:
            attempt += 1
            self._check_circuit(host)
            try:
                response = await self._send_once(request)
            except (httpx.TimeoutException, httpx.RequestError) as e:
                self._record_failure(host)
                if attempt > retries_allowed:
                    raise
                await self._back_off(attempt, retries_allowed, request, None, e)
                continue
            if response.status_code in self.retry_statuses and attempt <= retries_allowed:
                self._record_failure(host)
                await self._back_off(attempt, retries_allowed, request, response, None)
                continue
            self._record_success(host)
            return response

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
