"""Runtime MCP server configuration helpers for the Admin UI."""

import json
import os
import re
from typing import Any

from redis.exceptions import RedisError

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

ALLOWED_TRANSPORTS = ("ws", "http", "stdio")
_NAME_RE = re.compile(r"^[A-Z0-9_]{1,32}$")
_SERVER_ENV_RE = re.compile(r"^MCP_SERVER_([A-Z0-9_]+)_(TRANSPORT|URL|TIMEOUT|AUTH_TOKEN)$")
_FALLBACK_STATE: dict[str, Any] = {"enable_mcp_model": None, "servers": {}}


def _redis_key() -> str:
    return tenant_key("admin_ui:mcp:config")


def _load_override(redis_conn: Any) -> dict[str, Any]:
    if not redis_conn:
        return {
            "enable_mcp_model": _FALLBACK_STATE["enable_mcp_model"],
            "servers": dict(_FALLBACK_STATE["servers"]),
        }
    try:
        raw = redis_conn.get(_redis_key())
        if not raw:
            return {"enable_mcp_model": None, "servers": {}}
        data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        if isinstance(data, dict):
            return {
                "enable_mcp_model": data.get("enable_mcp_model"),
                "servers": dict(data.get("servers") or {}),
            }
    except (RedisError, json.JSONDecodeError):
        pass
    return {"enable_mcp_model": None, "servers": {}}


def _save_override(redis_conn: Any, payload: dict[str, Any]) -> None:
    _FALLBACK_STATE["enable_mcp_model"] = payload.get("enable_mcp_model")
    _FALLBACK_STATE["servers"] = dict(payload.get("servers") or {})
    if not redis_conn:
        return
    try:
        redis_conn.set(_redis_key(), json.dumps(payload))
    except RedisError:
        pass


def _apply_env_field(entry: dict[str, Any], field: str, value: str) -> None:
    if field == "TRANSPORT":
        entry["transport"] = value.strip().lower() or "ws"
    elif field == "URL":
        entry["url"] = value.strip()
    elif field == "TIMEOUT":
        try:
            entry["timeout"] = max(1, int(value))
        except ValueError:
            entry["timeout"] = 30
    elif field == "AUTH_TOKEN":
        entry["token_configured"] = bool(value.strip())


def _env_servers() -> dict[str, dict[str, Any]]:
    servers: dict[str, dict[str, Any]] = {}
    for key, value in os.environ.items():
        match = _SERVER_ENV_RE.match(key)
        if not match:
            continue
        name, field = match.group(1), match.group(2)
        entry = servers.setdefault(
            name,
            {"name": name, "transport": "ws", "url": "", "timeout": 30, "token_configured": False},
        )
        _apply_env_field(entry, field, value)
    return servers


def get_mcp_state() -> dict[str, Any]:
    """Return non-secret MCP configuration state for rendering the MCP Servers page."""
    redis_conn = get_redis_connection()
    override = _load_override(redis_conn)
    servers = _env_servers()
    for name, cfg in override["servers"].items():
        if cfg.get("removed"):
            servers.pop(name, None)
            continue
        servers[name] = {
            "name": name,
            "transport": cfg.get("transport", "ws"),
            "url": cfg.get("url", ""),
            "timeout": cfg.get("timeout", 30),
            "token_configured": bool(cfg.get("token_configured") or servers.get(name, {}).get("token_configured")),
        }
    enabled_raw = override["enable_mcp_model"]
    if enabled_raw is None:
        enabled_raw = os.getenv("ENABLE_MCP_MODEL", "false")
    enabled = str(enabled_raw).strip().lower() == "true"
    ordered = [servers[k] for k in sorted(servers)]
    return {"enable_mcp_model": enabled, "servers": ordered}


def set_mcp_enabled(enabled: bool) -> None:
    redis_conn = get_redis_connection()
    override = _load_override(redis_conn)
    override["enable_mcp_model"] = "true" if enabled else "false"
    os.environ["ENABLE_MCP_MODEL"] = override["enable_mcp_model"]
    _save_override(redis_conn, override)


def _parse_timeout(timeout_raw: str) -> int:
    try:
        timeout = int(timeout_raw.strip() or "30")
    except ValueError as exc:
        raise ValueError("Timeout must be an integer.") from exc
    if timeout < 1 or timeout > 300:
        raise ValueError("Timeout must be between 1 and 300 seconds.")
    return timeout


def _validate_server_inputs(
    name: str, transport: str, url: str, timeout_raw: str
) -> tuple[str, str, str, int]:
    norm_name = name.strip().upper().replace("-", "_")
    if not _NAME_RE.match(norm_name):
        raise ValueError("Server name must be 1-32 uppercase letters, digits, or underscores.")
    norm_transport = transport.strip().lower()
    if norm_transport not in ALLOWED_TRANSPORTS:
        raise ValueError(f"Transport must be one of: {', '.join(ALLOWED_TRANSPORTS)}.")
    clean_url = url.strip()
    if not clean_url:
        raise ValueError("Server URL or command is required.")
    if norm_transport in {"ws", "http"} and not re.match(r"^(wss?|https?)://", clean_url, re.IGNORECASE):
        raise ValueError("URL must start with ws://, wss://, http://, or https://.")
    return norm_name, norm_transport, clean_url, _parse_timeout(timeout_raw)


def upsert_mcp_server(name: str, transport: str, url: str, timeout_raw: str, auth_token: str = "") -> None:
    norm_name, norm_transport, clean_url, timeout = _validate_server_inputs(
        name, transport, url, timeout_raw
    )
    redis_conn = get_redis_connection()
    override = _load_override(redis_conn)
    prev = override["servers"].get(norm_name, {})
    token_configured = bool(auth_token.strip()) or bool(prev.get("token_configured")) or bool(
        os.getenv(f"MCP_SERVER_{norm_name}_AUTH_TOKEN", "").strip()
    )
    override["servers"][norm_name] = {
        "transport": norm_transport,
        "url": clean_url,
        "timeout": timeout,
        "token_configured": token_configured,
    }
    os.environ[f"MCP_SERVER_{norm_name}_TRANSPORT"] = norm_transport
    os.environ[f"MCP_SERVER_{norm_name}_URL"] = clean_url
    os.environ[f"MCP_SERVER_{norm_name}_TIMEOUT"] = str(timeout)
    if auth_token.strip():
        os.environ[f"MCP_SERVER_{norm_name}_AUTH_TOKEN"] = auth_token.strip()
    _save_override(redis_conn, override)


def remove_mcp_server(name: str) -> None:
    norm_name = name.strip().upper().replace("-", "_")
    if not _NAME_RE.match(norm_name):
        raise ValueError("Invalid server name.")
    redis_conn = get_redis_connection()
    override = _load_override(redis_conn)
    override["servers"][norm_name] = {"removed": True}
    for suffix in ("TRANSPORT", "URL", "TIMEOUT", "AUTH_TOKEN"):
        os.environ.pop(f"MCP_SERVER_{norm_name}_{suffix}", None)
    _save_override(redis_conn, override)
