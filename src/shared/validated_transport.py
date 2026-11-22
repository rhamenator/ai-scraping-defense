"""An httpx transport that connects only to public addresses it has just resolved and checked (#1905).

The URL keeps its hostname, so the ``Host`` header, TLS server name and certificate verification, connection pooling
and cookie scope all stay per hostname. The address check happens where the socket is opened: the name is resolved,
every address must be public, and the connection goes to one of those addresses (the next one if the first is
unreachable). A DNS answer that changes between an earlier check and the connection therefore has no effect, and a name
that resolves to an internal address is refused whatever the URL looked like.

When an HTTP(S) proxy is configured through the environment the proxy makes the connection and this check does not see
it; that is httpx's behaviour for proxies and is not changed here.
"""

import asyncio
from typing import Any, Iterable, Optional

import httpcore
import httpx

from .ssrf_protection import resolve_public_addresses

_CONNECT_ERRORS = (httpcore.ConnectError, httpcore.ConnectTimeout)


class ValidatedBackend(httpcore.AnyIOBackend):
    """Resolves, checks and connects in one step, trying each validated address in turn."""

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: Optional[Iterable] = None,
    ) -> httpcore.AsyncNetworkStream:
        addresses = await asyncio.to_thread(resolve_public_addresses, host, port)
        last_error: Exception = httpcore.ConnectError(f"no address to connect to for {host}")
        for address in addresses:
            try:
                return await super().connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except _CONNECT_ERRORS as exc:
                last_error = exc
        raise last_error


class ValidatedTransport(httpx.AsyncHTTPTransport):
    """``httpx.AsyncHTTPTransport`` whose connection pool uses :class:`ValidatedBackend`."""

    def __init__(
        self,
        *,
        verify: Any = True,
        http2: bool = False,
        limits: Optional[httpx.Limits] = None,
    ) -> None:
        super().__init__(verify=verify, http2=http2, limits=limits or httpx.Limits())
        limits = limits or httpx.Limits()
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(verify=verify),
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            http1=True,
            http2=http2,
            network_backend=ValidatedBackend(),
        )
