"""Runtime MCP server configuration helpers for the Admin UI."""

import json
import os
import re
import shlex
from typing import Any
from urllib.parse import urlparse

from redis.exceptions import RedisError

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

ALLOWED_TRANSPORTS = ("ws", "http", "stdio")
_NAME_RE = re.compile(r"^[A-Z0-9_]{1,32}$")
_SERVER_ENV_RE = re.compile(
    r"^MCP_SERVER_([A-Z0-9_]+)_(TRANSPORT|URL|EXECUTABLE|ARGS|TIMEOUT|AUTH_TOKEN)$"
)
_FALLBACK_STATE: dict[str, Any] = {"enable_mcp_model": None, "servers": {}, "version": 0}
_FALLBACK_TOKENS: dict[str, str] = {}


def _redis_key() -> str:
    return tenant_key("admin_ui:mcp:config")


def _tokens_key() -> str:
    return tenant_key("admin_ui:mcp:tokens")


def _load_override(redis_conn: Any) -> dict[str, Any]:
    if not redis_conn:
        return {
            "enable_mcp_model": _FALLBACK_STATE["enable_mcp_model"],
            "servers": dict(_FALLBACK_STATE["servers"]),
            "version": _FALLBACK_STATE.get("version", 0),
        }
    try:
        raw = redis_conn.get(_redis_key())
        if raw:
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            if isinstance(data, dict):
                return {
                    "enable_mcp_model": data.get("enable_mcp_model"),
                    "servers": dict(data.get("servers") or {}),
                    "version": int(data.get("version") or 0),
                }
    except (RedisError, json.JSONDecodeError, ValueError, TypeError):
        pass
    return {"enable_mcp_model": None, "servers": {}, "version": 0}


def _save_override(redis_conn: Any, payload: dict[str, Any]) -> None:
    payload["version"] = int(payload.get("version") or 0) + 1
    _FALLBACK_STATE["enable_mcp_model"] = payload.get("enable_mcp_model")
    _FALLBACK_STATE["servers"] = dict(payload.get("servers") or {})
    _FALLBACK_STATE["version"] = payload["version"]
    if not redis_conn:
        return
    try:
        redis_conn.set(_redis_key(), json.dumps(payload))
    except RedisError:
        pass


def _load_tokens(redis_conn: Any) -> dict[str, str]:
    if not redis_conn:
        return dict(_FALLBACK_TOKENS)
    try:
        raw = redis_conn.get(_tokens_key())
        if raw:
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if v}
    except (RedisError, json.JSONDecodeError):
        pass
    return {}


def _save_token(redis_conn: Any, name: str, secret_value: str | None) -> None:
    tokens = _load_tokens(redis_conn)
    if secret_value is None:
        tokens.pop(name, None)
        _FALLBACK_TOKENS.pop(name, None)
    else:
        tokens[name] = secret_value
        _FALLBACK_TOKENS[name] = secret_value
    if not redis_conn:
        return
    try:
        redis_conn.set(_tokens_key(), json.dumps(tokens))
    except RedisError:
        pass


def _safe_int_timeout(value: str) -> int:
    try:
        return max(1, int(value))
    except ValueError:
        return 30


def _apply_env_field(entry: dict[str, Any], field: str, value: str) -> None:
    if field == "TRANSPORT":
        entry["transport"] = value.strip().lower() or "ws"
    elif field in {"URL", "EXECUTABLE"}:
        entry["url"] = value.strip()
    elif field == "ARGS" and value.strip():
        entry["args_str"] = value.strip()
    elif field == "TIMEOUT":
        entry["timeout"] = _safe_int_timeout(value)
    elif field == "AUTH_TOKEN":
        entry["has_auth"] = bool(value.strip())


def _env_servers() -> dict[str, dict[str, Any]]:
    servers: dict[str, dict[str, Any]] = {}
    for key, value in os.environ.items():
        match = _SERVER_ENV_RE.match(key)
        if not match:
            continue
        name, field = match.group(1), match.group(2)
        entry = servers.setdefault(
            name,
            {"name": name, "transport": "ws", "url": "", "timeout": 30, "has_auth": False},
        )
        _apply_env_field(entry, field, value)
    for entry in servers.values():
        args_str = entry.pop("args_str", "")
        if entry["transport"] == "stdio" and args_str:
            entry["url"] = f"{entry['url']} {args_str}".strip()
    return servers


def get_mcp_state() -> dict[str, Any]:
    """Return non-secret MCP configuration state for rendering the MCP Servers page."""
    redis_conn = get_redis_connection()
    override = _load_override(redis_conn)
    tokens = _load_tokens(redis_conn)
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
            "has_auth": bool(
                cfg.get("has_auth")
                or tokens.get(name)
                or servers.get(name, {}).get("has_auth")
            ),
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
    if norm_transport in {"ws", "http"}:
        scheme = urlparse(clean_url).scheme.lower()
        if scheme not in {"ws", "wss", "http", "https"}:
            raise ValueError("URL must use a ws, wss, http, or https scheme.")
    return norm_name, norm_transport, clean_url, _parse_timeout(timeout_raw)


def _sync_server_env(norm_name: str, norm_transport: str, record: dict[str, Any], secret_val: str) -> None:
    os.environ[f"MCP_SERVER_{norm_name}_TRANSPORT"] = norm_transport
    os.environ[f"MCP_SERVER_{norm_name}_TIMEOUT"] = str(record["timeout"])
    if norm_transport == "stdio":
        os.environ.pop(f"MCP_SERVER_{norm_name}_URL", None)
        os.environ[f"MCP_SERVER_{norm_name}_EXECUTABLE"] = record["executable"]
        os.environ[f"MCP_SERVER_{norm_name}_ARGS"] = shlex.join(record["args"])
    else:
        os.environ.pop(f"MCP_SERVER_{norm_name}_EXECUTABLE", None)
        os.environ.pop(f"MCP_SERVER_{norm_name}_ARGS", None)
        os.environ[f"MCP_SERVER_{norm_name}_URL"] = record["url"]
    if secret_val:
        os.environ[f"MCP_SERVER_{norm_name}_AUTH_TOKEN"] = secret_val


def upsert_mcp_server(
    name: str, transport: str, url: str, timeout_raw: str, auth_token: str | None = None
) -> None:
    norm_name, norm_transport, clean_url, timeout = _validate_server_inputs(
        name, transport, url, timeout_raw
    )
    redis_conn = get_redis_connection()
    override = _load_override(redis_conn)
    tokens = _load_tokens(redis_conn)
    prev = override["servers"].get(norm_name, {})
    clean_secret = (auth_token or "").strip()
    has_auth = bool(
        clean_secret
        or prev.get("has_auth")
        or tokens.get(norm_name)
        or os.getenv(f"MCP_SERVER_{norm_name}_AUTH_TOKEN", "").strip()
    )
    record: dict[str, Any] = {
        "transport": norm_transport,
        "url": clean_url,
        "timeout": timeout,
        "has_auth": has_auth,
    }
    if norm_transport == "stdio":
        parts = shlex.split(clean_url)
        if not parts:
            raise ValueError("Subprocess command is required.")
        record["executable"] = parts[0]
        record["args"] = parts[1:]
    override["servers"][norm_name] = record
    if clean_secret:
        _save_token(redis_conn, norm_name, clean_secret)
    _sync_server_env(norm_name, norm_transport, record, clean_secret)
    _save_override(redis_conn, override)


def remove_mcp_server(name: str) -> None:
    norm_name = name.strip().upper().replace("-", "_")
    if not _NAME_RE.match(norm_name):
        raise ValueError("Invalid server name.")
    redis_conn = get_redis_connection()
    override = _load_override(redis_conn)
    override["servers"][norm_name] = {"removed": True}
    _save_token(redis_conn, norm_name, None)
    for suffix in ("TRANSPORT", "URL", "EXECUTABLE", "ARGS", "TIMEOUT", "AUTH_TOKEN"):
        os.environ.pop(f"MCP_SERVER_{norm_name}_{suffix}", None)
    _save_override(redis_conn, override)
