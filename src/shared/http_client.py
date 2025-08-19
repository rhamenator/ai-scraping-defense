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

import logging
from typing import Any, Dict, Optional, Union

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    # Create a stub for development environments without httpx
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


logger = logging.getLogger(__name__)


class AsyncHttpClient:
    """Async context-managed HTTP client abstraction using httpx.AsyncClient.
    
    Provides a clean interface for making HTTP requests with proper connection
    lifecycle management, configurable timeouts, and helper methods for common
    operations like JSON POST requests.
    
    Attributes:
        timeout (float): Default timeout in seconds for HTTP requests
        follow_redirects (bool): Whether to follow HTTP redirects
        verify (bool): Whether to verify SSL certificates
        limits (httpx.Limits): Connection pool limits configuration
    """
    
    def __init__(
        self, 
        timeout: float = 30.0,
        follow_redirects: bool = True,
        verify: bool = True,
        max_connections: int = 100,
        max_keepalive_connections: int = 20
    ):
        """Initialize the HTTP client with configuration.
        
        Args:
            timeout: Default timeout in seconds for all requests
            follow_redirects: Whether to automatically follow redirects
            verify: Whether to verify SSL certificates
            max_connections: Maximum number of connections in the pool
            max_keepalive_connections: Maximum number of keep-alive connections
        """
        if not HTTPX_AVAILABLE:
            logger.warning("httpx not available. HTTP client functionality will be limited.")
        
        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self.verify = verify
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self) -> 'AsyncHttpClient':
        """Enter the async context and initialize the HTTP client."""
        if not HTTPX_AVAILABLE:
            logger.error("Cannot create HTTP client: httpx not available")
            return self
        
        try:
            # Create connection limits for the client
            limits = httpx.Limits(
                max_connections=self.max_connections,
                max_keepalive_connections=self.max_keepalive_connections
            )
            
            # Initialize the httpx client with our configuration
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=self.follow_redirects,
                verify=self.verify,
                limits=limits
            )
            
            logger.debug(
                f"HTTP client initialized with timeout={self.timeout}s, "
                f"max_connections={self.max_connections}, "
                f"max_keepalive={self.max_keepalive_connections}"
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
    
    async def async_post_json(
        self,
        url: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> httpx.Response:
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
            httpx.RequestError: For network-related errors
            httpx.TimeoutException: If the request times out
            httpx.HTTPStatusError: For HTTP status errors (4xx, 5xx)
        """
        if not self.is_available:
            raise RuntimeError("HTTP client is not available or not initialized")
        
        # Set default headers for JSON requests
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        
        # Use provided timeout or fall back to instance default
        request_timeout = timeout if timeout is not None else self.timeout
        
        try:
            logger.debug(f"Making JSON POST request to {url}")
            response = await self._client.post(
                url,
                json=data,
                headers=request_headers,
                timeout=request_timeout
            )
            
            logger.debug(
                f"Received response: {response.status_code} from {url} "
                f"(Content-Length: {len(response.content)} bytes)"
            )
            
            return response
            
        except httpx.TimeoutException as e:
            logger.error(f"Timeout making POST request to {url}: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error making POST request to {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error making POST request to {url}: {e}")
            raise
    
    async def async_get(
        self,
        url: str,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> httpx.Response:
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
            httpx.RequestError: For network-related errors
            httpx.TimeoutException: If the request times out
            httpx.HTTPStatusError: For HTTP status errors (4xx, 5xx)
        """
        if not self.is_available:
            raise RuntimeError("HTTP client is not available or not initialized")
        
        request_timeout = timeout if timeout is not None else self.timeout
        
        try:
            logger.debug(f"Making GET request to {url}")
            response = await self._client.get(
                url,
                params=params,
                headers=headers,
                timeout=request_timeout
            )
            
            logger.debug(
                f"Received response: {response.status_code} from {url} "
                f"(Content-Length: {len(response.content)} bytes)"
            )
            
            return response
            
        except httpx.TimeoutException as e:
            logger.error(f"Timeout making GET request to {url}: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error making GET request to {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error making GET request to {url}: {e}")
            raise