"""Utilities for interacting with Model Context Protocol (MCP) servers."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency import
    from mcp import ClientSession
    from mcp.transport import StdioClientTransport, WebSocketClientTransport
except ImportError:  # pragma: no cover - handled at runtime
    ClientSession = None
    WebSocketClientTransport = None
    StdioClientTransport = None


class MCPClientError(RuntimeError):
    """Raised when the MCP client cannot complete a request."""


@dataclass(frozen=True)
class MCPServerConfig:
    """Runtime configuration for connecting to an MCP server."""

    label: str
    transport: str
    endpoint: Optional[str] = None
    executable: Optional[str] = None
    args: list[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    session_name: str = "ai-scraping-defense"
    timeout: float = 30.0


def parse_mcp_uri(model_uri: str) -> tuple[str, str, Dict[str, str]]:
    """Parse ``mcp://<label>/<tool>?k=v`` URIs used by adapters.

    Returns a tuple of ``(server_label, tool_name, query_params)``.
    Raises ``ValueError`` if the URI is malformed.
    """

    parsed = urlparse(model_uri)
    if parsed.scheme != "mcp":
        raise ValueError(f"Unsupported MCP URI scheme: {parsed.scheme}")
    server_label = parsed.netloc or ""
    tool_name = parsed.path.lstrip("/")
    if not server_label or not tool_name:
        raise ValueError(f"Invalid MCP URI '{model_uri}'. Expected mcp://label/tool format")
    query = {key: values[-1] for key, values in parse_qs(parsed.query, keep_blank_values=True).items()}
    return server_label, tool_name, query


def _json_to_mapping(raw: Any, description: str) -> Dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, Mapping):
                return {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError as exc:
            logger.warning("Failed to decode %s JSON: %s", description, exc)
    return {}


def load_server_config(
    label: str,
    overrides: Optional[Dict[str, Any]] = None,
    adapter_config: Optional[Dict[str, Any]] = None,
) -> MCPServerConfig:
    """Build an ``MCPServerConfig`` from environment variables and overrides."""

    overrides = overrides or {}
    adapter_config = adapter_config or {}
    prefix = f"MCP_SERVER_{label.upper()}_"

    def _first_non_empty(*values: Any) -> Optional[Any]:
        for value in values:
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return value
        return None

    raw_transport = _first_non_empty(
        overrides.get("transport"),
        adapter_config.get("transport"),
        os.getenv(f"{prefix}TRANSPORT"),
        os.getenv("MCP_DEFAULT_TRANSPORT"),
        "ws",
    )
    transport = str(raw_transport).lower()

    timeout_value = _first_non_empty(
        overrides.get("timeout"),
        adapter_config.get("timeout"),
        os.getenv(f"{prefix}TIMEOUT"),
        os.getenv("MCP_DEFAULT_TIMEOUT"),
    )
    try:
        timeout = float(timeout_value) if timeout_value is not None else 30.0
    except (TypeError, ValueError):
        timeout = 30.0

    endpoint = _first_non_empty(
        overrides.get("endpoint") or overrides.get("url"),
        adapter_config.get("endpoint") or adapter_config.get("url"),
        os.getenv(f"{prefix}URL"),
        os.getenv(f"{prefix}ENDPOINT"),
    )

    executable = _first_non_empty(
        overrides.get("executable"),
        adapter_config.get("executable"),
        os.getenv(f"{prefix}EXECUTABLE"),
    )

    args_value = _first_non_empty(
        overrides.get("args"),
        adapter_config.get("args"),
        os.getenv(f"{prefix}ARGS"),
    )
    if isinstance(args_value, str):
        args = shlex.split(args_value)
    elif isinstance(args_value, (list, tuple)):
        args = [str(item) for item in args_value]
    else:
        args = []

    env_mapping = _json_to_mapping(
        _first_non_empty(
            overrides.get("env"),
            adapter_config.get("env"),
            os.getenv(f"{prefix}ENV_JSON"),
        ),
        f"MCP server '{label}' environment",
    )

    headers_mapping = _json_to_mapping(
        _first_non_empty(
            overrides.get("headers"),
            adapter_config.get("headers"),
            os.getenv(f"{prefix}HEADERS_JSON"),
        ),
        f"MCP server '{label}' headers",
    )

    auth_token = _first_non_empty(
        overrides.get("auth_token"),
        adapter_config.get("auth_token"),
        os.getenv(f"{prefix}AUTH_TOKEN"),
    )
    if auth_token and "Authorization" not in headers_mapping:
        headers_mapping["Authorization"] = f"Bearer {auth_token}"

    session_name = str(
        _first_non_empty(
            overrides.get("client_name"),
            adapter_config.get("client_name"),
            os.getenv(f"{prefix}CLIENT_NAME"),
            "ai-scraping-defense",
        )
    )

    if transport in {"ws", "wss", "websocket"}:
        if not endpoint:
            raise MCPClientError(
                f"MCP server '{label}' requires MCP_SERVER_{label.upper()}_URL for websocket transport"
            )
    elif transport in {"stdio", "process"}:
        if not executable:
            raise MCPClientError(
                f"MCP server '{label}' requires MCP_SERVER_{label.upper()}_EXECUTABLE for stdio transport"
            )
    else:
        raise MCPClientError(f"Unsupported MCP transport '{transport}' for server '{label}'")

    return MCPServerConfig(
        label=label,
        transport=transport,
        endpoint=str(endpoint) if endpoint else None,
        executable=str(executable) if executable else None,
        args=args,
        env=env_mapping,
        headers=headers_mapping,
        session_name=session_name,
        timeout=timeout,
    )


class MCPClient:
    """Thin wrapper that performs synchronous MCP tool invocations."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._background_loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_lock = threading.Lock()

    def call_tool(self, tool_name: str, arguments: Any, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Invoke ``tool_name`` with ``arguments`` and return a JSON-serialisable dict."""

        effective_timeout = timeout or self.config.timeout
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop and running_loop.is_running():
            loop = self._ensure_background_loop()
            future = asyncio.run_coroutine_threadsafe(
                self._call_tool(tool_name, arguments, effective_timeout), loop
            )
            try:
                return future.result(timeout=effective_timeout)
            except Exception as exc:  # pragma: no cover - surfaced as MCPClientError below
                raise MCPClientError(str(exc)) from exc
        return asyncio.run(self._call_tool(tool_name, arguments, effective_timeout))

    def _ensure_background_loop(self) -> asyncio.AbstractEventLoop:
        with self._loop_lock:
            if self._background_loop is not None:
                return self._background_loop
            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=self._loop_entry, args=(loop,), daemon=True)
            thread.start()
            self._background_loop = loop
            self._loop_thread = thread
            return loop

    @staticmethod
    def _loop_entry(loop: asyncio.AbstractEventLoop) -> None:  # pragma: no cover - background loop
        asyncio.set_event_loop(loop)
        loop.run_forever()

    async def _call_tool(self, tool_name: str, arguments: Any, timeout: float) -> Dict[str, Any]:
        if ClientSession is None:
            raise MCPClientError(
                "mcp package is not installed. Run 'pip install mcp'."
            )
        transport = await self._create_transport()
        try:
            if hasattr(transport, "__aenter__"):
                async with transport:  # type: ignore[attr-defined]
                    return await self._invoke_session(tool_name, arguments, transport, timeout)
            return await self._invoke_session(tool_name, arguments, transport, timeout)
        finally:
            close = getattr(transport, "close", None)
            if asyncio.iscoroutinefunction(close):  # pragma: no cover - depends on implementation
                try:
                    await close()  # type: ignore[call-arg]
                except Exception:  # pragma: no cover - best effort cleanup
                    logger.debug("Failed to close MCP transport", exc_info=True)

    async def _invoke_session(
        self,
        tool_name: str,
        arguments: Any,
        transport: Any,
        timeout: float,
    ) -> Dict[str, Any]:
        async with ClientSession(self.config.session_name, transport) as session:  # type: ignore[arg-type]
            try:
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments=arguments or {}),
                    timeout=timeout,
                )
            except asyncio.TimeoutError as exc:
                raise MCPClientError(
                    f"Timed out calling MCP tool '{tool_name}' after {timeout:.1f}s"
                ) from exc
            except Exception as exc:  # pragma: no cover - depends on MCP library errors
                raise MCPClientError(f"MCP tool '{tool_name}' failed: {exc}") from exc
            return _normalise_tool_result(result)

    async def _create_transport(self) -> Any:
        transport_type = self.config.transport
        if transport_type in {"ws", "wss", "websocket"}:
            if WebSocketClientTransport is None:
                raise MCPClientError(
                    "WebSocket transport requires the mcp websocket extra."
                )
            return WebSocketClientTransport(self.config.endpoint, headers=self.config.headers or None)  # type: ignore[arg-type]
        if transport_type in {"stdio", "process"}:
            if StdioClientTransport is None:
                raise MCPClientError(
                    "Stdio transport requires the mcp stdio extra."
                )
            command = [self.config.executable] + self.config.args if self.config.executable else self.config.args
            return StdioClientTransport(command=command, env=self.config.env or None)  # type: ignore[arg-type]
        raise MCPClientError(f"Unsupported MCP transport '{transport_type}'")


def _normalise_tool_result(result: Any) -> Dict[str, Any]:
    if result is None:
        return {}
    if isinstance(result, Mapping):
        return dict(result)
    if hasattr(result, "model_dump"):
        try:
            return result.model_dump()  # type: ignore[return-value]
        except Exception:  # pragma: no cover - defensive
            pass
    if hasattr(result, "dict"):
        try:
            return result.dict()  # type: ignore[return-value]
        except Exception:  # pragma: no cover - defensive
            pass
    return {"raw": repr(result)}


def call_mcp_tool(
    model_uri: str,
    arguments: Any,
    *,
    config_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience wrapper that parses ``model_uri`` and executes an MCP tool call."""

    server_label, tool_name, query = parse_mcp_uri(model_uri)
    merged_overrides: Dict[str, Any] = dict(query)
    if config_overrides:
        merged_overrides.update({k: v for k, v in config_overrides.items() if v is not None})
    config = load_server_config(server_label, overrides=merged_overrides, adapter_config=config_overrides)
    client = MCPClient(config)
    return client.call_tool(tool_name, arguments, timeout=config.timeout)


__all__ = [
    "MCPClient",
    "MCPClientError",
    "MCPServerConfig",
    "call_mcp_tool",
    "load_server_config",
    "parse_mcp_uri",
]
