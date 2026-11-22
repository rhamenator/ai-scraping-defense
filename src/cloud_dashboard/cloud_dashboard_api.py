async def get_metrics(installation_id: str, request: Request):
    redis_conn, principal, error = _authenticate_request(request)
    if error:
        return error
    installation_id = _validate_installation_id(installation_id)
    if not installation_id:
        return JSONResponse({"error": "invalid installation_id"}, status_code=400)
"""FastAPI service for hosted monitoring across installations."""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any, Dict, List

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from starlette.websockets import WebSocketState

from src.shared.api_key_auth import is_api_key_valid, load_api_key
from src.shared.audit import log_event
from src.shared.config import tenant_key
from src.shared.metrics import OPERATIONAL_EVENTS, SECURITY_EVENTS
from src.shared.middleware import create_app
from src.shared.observability import (
    HealthCheckResult,
    WebSocketConnectionLimiter,
    register_health_check,
    trace_span,
)
from src.shared.redis_client import get_redis_connection

logger = logging.getLogger(__name__)

# Redis-backed storage of metrics per installation with TTLs
METRICS_TTL = 60
REGISTRATION_TTL = 86400  # 24h registration marker by default
WATCHERS: Dict[str, List[WebSocket]] = {}
WATCHERS_LOCK = asyncio.Lock()

WEBSOCKET_METRICS_INTERVAL = 5
WATCHERS_CLEANUP_INTERVAL = 60
MAX_INSTALLATION_ID_LENGTH = int(
    os.getenv("CLOUD_DASHBOARD_MAX_INSTALLATION_ID", "128")
)
MAX_METRICS_KEYS = int(os.getenv("CLOUD_DASHBOARD_MAX_METRICS_KEYS", "200"))
MAX_METRIC_KEY_LENGTH = int(os.getenv("CLOUD_DASHBOARD_MAX_METRIC_KEY_LENGTH", "64"))
MAX_WEBSOCKET_CONNECTIONS = int(os.getenv("CLOUD_DASHBOARD_WS_MAX_CONNECTIONS", "100"))
MAX_WEBSOCKET_CONNECTIONS_PER_INSTALLATION = int(
    os.getenv("CLOUD_DASHBOARD_WS_MAX_CONNECTIONS_PER_INSTALLATION", "5")
)
MAX_WEBSOCKET_MESSAGE_BYTES = int(
    os.getenv("CLOUD_DASHBOARD_WS_MAX_MESSAGE_BYTES", "65536")
)
WEBSOCKET_LIMITER = WebSocketConnectionLimiter(
    max_total=MAX_WEBSOCKET_CONNECTIONS,
    max_per_key=MAX_WEBSOCKET_CONNECTIONS_PER_INSTALLATION,
)


def _validate_installation_id(installation_id: Any) -> str | None:
    if not isinstance(installation_id, str) or not installation_id:
        return None
    if len(installation_id) > MAX_INSTALLATION_ID_LENGTH:
        return None
    return installation_id


def _validate_metrics(metrics: Any) -> bool:
    if not isinstance(metrics, dict):
        return False
    if len(metrics) > MAX_METRICS_KEYS:
        return False
    for key in metrics.keys():
        if not isinstance(key, str) or len(key) > MAX_METRIC_KEY_LENGTH:
            return False
    return True


def _websocket_close_try_again_later() -> int:
    return 1013


def _client_ip(websocket: WebSocket) -> str:
    client = websocket.client
    return client.host if client and client.host else "unknown"


# Each kind of per-installation state lives under its own prefix. Installation ids are chosen by operators and may contain
# ":", so a metrics key built from an id must never be able to equal a registration or credential key built from another id
# (for example an id "credential:victim" writing the credential record of "victim"). Metrics keys therefore do not sit under
# the registration prefix, and credentials have a prefix of their own (#1901).
def _metrics_key(installation_id: str) -> str:
    return tenant_key(f"cloud:metrics:{installation_id}")


def _registration_key(installation_id: str) -> str:
    return tenant_key(f"cloud:install:registered:{installation_id}")


def _is_registered_installation(redis_conn: Any, installation_id: str) -> bool:
    if not redis_conn:
        return False
    return bool(redis_conn.get(_registration_key(installation_id)))


def _record_websocket_event(action: str, **details) -> None:
    OPERATIONAL_EVENTS.labels(event_type=f"cloud_dashboard_ws_{action}").inc()
    log_event("cloud_dashboard", f"cloud_dashboard_websocket_{action}", details)


def _record_websocket_security_event(action: str, **details) -> None:
    SECURITY_EVENTS.labels(event_type=f"cloud_dashboard_ws_{action}").inc()
    log_event("cloud_dashboard", f"cloud_dashboard_websocket_{action}", details)


async def _send_limited_json(
    websocket: WebSocket, payload: dict, *, installation_id: str
) -> bool:
    encoded = json.dumps(payload, default=str).encode("utf-8")
    if MAX_WEBSOCKET_MESSAGE_BYTES and len(encoded) > MAX_WEBSOCKET_MESSAGE_BYTES:
        _record_websocket_security_event(
            "payload_too_large",
            installation_id=installation_id,
            client_ip=_client_ip(websocket),
            payload_bytes=len(encoded),
            max_bytes=MAX_WEBSOCKET_MESSAGE_BYTES,
        )
        await websocket.send_json({"error": "Metrics payload too large"})
        await websocket.close(code=_websocket_close_try_again_later())
        return False
    await websocket.send_json(payload)
    return True


async def _cleanup_stale_watchers() -> None:
    while True:
        await asyncio.sleep(WATCHERS_CLEANUP_INTERVAL)
        async with WATCHERS_LOCK:
            for inst_id, sockets in list(WATCHERS.items()):
                WATCHERS[inst_id] = [
                    ws
                    for ws in sockets
                    if ws.client_state == WebSocketState.CONNECTED
                    and ws.application_state == WebSocketState.CONNECTED
                ]
                if not WATCHERS[inst_id]:
                    WATCHERS.pop(inst_id, None)


@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover - startup/shutdown hook
    app.state.watchers_cleanup_task = asyncio.create_task(_cleanup_stale_watchers())
    try:
        yield
    finally:
        task = getattr(app.state, "watchers_cleanup_task", None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.debug("Watcher cleanup task cancelled during shutdown")


app = create_app(lifespan=lifespan)


@register_health_check(app, "cloud_dashboard_redis", critical=True)
async def _redis_health() -> HealthCheckResult:
    redis_conn = get_redis_connection()
    if not redis_conn:
        return HealthCheckResult.unhealthy({"reason": "redis unavailable"})
    try:
        redis_conn.ping()
    except RedisError as exc:  # pragma: no cover - network IO
        return HealthCheckResult.unhealthy({"error": str(exc)})
    return HealthCheckResult.healthy()


API_KEY = load_api_key("CLOUD_DASHBOARD_API_KEY")


def _authorize_api_key(provided: str | None) -> JSONResponse | None:
    if not API_KEY:
        logger.error("CLOUD_DASHBOARD_API_KEY is not configured; denying request")
        return JSONResponse(
            {
                "error": "CLOUD_DASHBOARD_API_KEY is not configured; "
                "run python scripts/interactive_setup.py"
            },
            status_code=503,
        )
    if not is_api_key_valid(provided, API_KEY):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


INSTALLATION_CREDENTIAL_HEADER = "X-Installation-Token"
# Opt-in compatibility for installations that still push with the shared key: the shared key (the operator credential)
# may then act for any installation, which is the old behaviour. Off by default (#1901).
ALLOW_SHARED_KEY = os.getenv("CLOUD_DASHBOARD_ALLOW_SHARED_KEY", "false").lower() == "true"


@dataclass(frozen=True)
class Principal:
    """Who is calling: the operator (global read), or one installation (only itself)."""

    kind: str  # "operator" | "installation"
    installation_id: str | None = None


def _credential_key(installation_id: str) -> str:
    return tenant_key(f"cloud:credential:{installation_id}")


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _issue_token(installation_id: str) -> tuple[str, str]:
    """A new credential for ``installation_id``: the token to hand over once, and the hash to store."""
    secret = secrets.token_urlsafe(32)
    return f"{installation_id}.{secret}", _hash_secret(secret)


def _split_token(token: str | None) -> tuple[str, str] | None:
    """``(installation_id, secret)`` from a token, or None. The id comes from the token, never from the request."""
    if not token or "." not in token:
        return None
    installation_id, secret = token.rsplit(".", 1)
    installation_id = _validate_installation_id(installation_id)
    return (installation_id, secret) if installation_id and secret else None


def _stored_hash(redis_conn: Any, installation_id: str) -> str:
    try:
        raw = redis_conn.get(_credential_key(installation_id))
    except RedisError:
        return ""
    try:
        return str(json.loads(raw).get("hash", "")) if raw else ""
    except (JSONDecodeError, AttributeError, TypeError):
        return ""


def _installation_from_token(redis_conn: Any, token: str | None) -> str | None:
    """The installation a valid token belongs to. Unknown ids and wrong secrets fail the same way."""
    parts = _split_token(token)
    if not parts or not redis_conn:
        return None
    installation_id, secret = parts
    stored = _stored_hash(redis_conn, installation_id)
    # Compare even when nothing is stored, so an unknown id does not answer faster than a wrong secret.
    matches = hmac.compare_digest(_hash_secret(secret), stored or "0" * 64)
    return installation_id if stored and matches else None


def _principal(headers: Any, redis_conn: Any) -> Principal | None:
    """Authenticate a request or websocket handshake from its headers; None means unauthenticated."""
    token = headers.get(INSTALLATION_CREDENTIAL_HEADER)
    if token:
        installation_id = _installation_from_token(redis_conn, token)
        return Principal("installation", installation_id) if installation_id else None
    if API_KEY and is_api_key_valid(headers.get("X-API-Key"), API_KEY):
        return Principal("operator")
    return None


def _may_access(principal: Principal, installation_id: str, *, write: bool) -> bool:
    """An installation reaches only itself. The operator reads any installation; writing for one needs the opt-in."""
    if principal.kind == "installation":
        return principal.installation_id == installation_id
    return ALLOW_SHARED_KEY or not write


def _deny(principal: Principal | None) -> JSONResponse:
    if principal is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return JSONResponse({"error": "forbidden"}, status_code=403)


def _authenticate_request(request: Request) -> tuple[Any, Principal | None, JSONResponse | None]:
    """Storage, caller and, when the request must stop here, the error response to send."""
    redis_conn = get_redis_connection()
    if not redis_conn:
        return None, None, JSONResponse({"error": "storage unavailable"}, status_code=500)
    principal = _principal(request.headers, redis_conn)
    if principal is None:
        return redis_conn, None, _authorize_api_key(request.headers.get("X-API-Key")) or _deny(None)
    return redis_conn, principal, None


def _push_target(principal: Principal, payload: Dict[str, Any]) -> tuple[str | None, Any]:
    """The installation and metrics of a push. An installation's id defaults to the one in its credential."""
    requested = payload.get("installation_id")
    if principal.kind == "installation" and requested in (None, ""):
        requested = principal.installation_id
    return _validate_installation_id(requested), payload.get("metrics")


def _read_target(principal: Principal, installation_id: str) -> tuple[str | None, JSONResponse | None]:
    """The installation to read, or the error response when it is malformed or not the caller's to read."""
    validated = _validate_installation_id(installation_id)
    if not validated:
        return None, JSONResponse({"error": "invalid installation_id"}, status_code=400)
    if not _may_access(principal, validated, write=False):
        return None, _deny(principal)
    return validated, None


def _websocket_denial(principal: Principal | None, installation_id: str) -> str | None:
    if principal is None:
        return "unauthenticated"
    if not _may_access(principal, installation_id, write=False):
        return "wrong_installation"
    return None


@app.post("/register")
async def register_installation(payload: Dict[str, Any], request: Request):
    """Register an installation.

    The operator key registers an installation and, the first time (or with ``"rotate": true``), returns its credential
    once; an installation presenting its own credential can refresh its registration. Nobody can register for another
    installation with an installation credential.
    """
    redis_conn, principal, error = _authenticate_request(request)
    if error:
        return error

    installation_id = _validate_installation_id(payload.get("installation_id"))
    if not installation_id:
        return JSONResponse({"error": "installation_id required"}, status_code=400)
    if principal.kind == "installation" and principal.installation_id != installation_id:
        return _deny(principal)

    try:
        with trace_span(
            "cloud_dashboard.register_installation",
            attributes={"installation_id": installation_id},
        ):
            token = _store_registration(redis_conn, installation_id, principal, bool(payload.get("rotate")))
    except RedisError:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)
    body: Dict[str, Any] = {"status": "registered", "installation_id": installation_id}
    if token:
        body["token"] = token  # shown once; only its hash is kept
    return body


def _store_registration(redis_conn: Any, installation_id: str, principal: Principal, rotate: bool) -> str | None:
    """Mark the installation registered; create or rotate its credential when the operator asks. Returns a new token."""
    redis_conn.set(
        _registration_key(installation_id),
        json.dumps({"registered": True}),
        ex=REGISTRATION_TTL,
    )
    if principal.kind != "operator":
        return None
    if not rotate and _stored_hash(redis_conn, installation_id):
        return None
    token, hashed = _issue_token(installation_id)
    redis_conn.set(
        _credential_key(installation_id),
        json.dumps({"hash": hashed, "created": int(time.time())}),
    )
    return token


@app.post("/metrics")
async def push_metrics(payload: Dict[str, Any], request: Request):
    redis_conn, principal, error = _authenticate_request(request)
    if error:
        return error

    # An installation's id is the one in its credential; a different id in the body is refused, never trusted.
    installation_id, metrics = _push_target(principal, payload)
    if not installation_id or not _validate_metrics(metrics):
        return JSONResponse({"error": "invalid payload"}, status_code=400)
    if not _may_access(principal, installation_id, write=True):
        return _deny(principal)
    key = _metrics_key(installation_id)
    try:
        with trace_span(
            "cloud_dashboard.push_metrics",
            attributes={"installation_id": installation_id},
        ):
            redis_conn.set(key, json.dumps(metrics), ex=METRICS_TTL)
    except RedisError:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)
    async with WATCHERS_LOCK:
        sockets = list(WATCHERS.get(installation_id, []))
    stale_sockets: list[WebSocket] = []
    for ws in sockets:
        try:
            if not await _send_limited_json(
                ws, metrics, installation_id=installation_id
            ):
                stale_sockets.append(ws)
        except Exception as e:
            # best-effort fanout
            logger.warning(f"WebSocket send_json failed during metrics fanout: {e}")
            stale_sockets.append(ws)
    if stale_sockets:
        async with WATCHERS_LOCK:
            remaining = WATCHERS.get(installation_id, [])
            WATCHERS[installation_id] = [
                ws for ws in remaining if ws not in stale_sockets
            ]
            if not WATCHERS[installation_id]:
                WATCHERS.pop(installation_id, None)
    return {"status": "ok"}


@app.get("/metrics/{installation_id}")
async def get_metrics(installation_id: str, request: Request):
    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "storage unavailable"}, status_code=500)
    principal = _principal(request.headers, redis_conn)
    if principal is None:
        return _authorize_api_key(request.headers.get("X-API-Key")) or _deny(None)
    installation_id, error = _read_target(principal, installation_id)
    if error:
        return error
    key = _metrics_key(installation_id)
    try:
        with trace_span(
            "cloud_dashboard.get_metrics",
            attributes={"installation_id": installation_id},
        ):
            raw = redis_conn.get(key)
    except RedisError:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)
    if raw:
        try:
            return json.loads(raw)
        except JSONDecodeError:
            return JSONResponse({"error": "corrupted metrics data"}, status_code=500)
    return {}


@app.websocket("/ws/{installation_id}")
async def metrics_websocket(websocket: WebSocket, installation_id: str):
    client_ip = _client_ip(websocket)
    if not _validate_installation_id(installation_id):
        _record_websocket_security_event(
            "denied",
            installation_id=installation_id,
            client_ip=client_ip,
            reason="invalid_installation_id",
        )
        await websocket.close(code=1008)
        return
    redis_conn = get_redis_connection()
    if not redis_conn:
        _record_websocket_security_event(
            "denied",
            installation_id=installation_id,
            client_ip=client_ip,
            reason="storage_unavailable",
        )
        await websocket.close(code=_websocket_close_try_again_later())
        return
    denial = _websocket_denial(_principal(websocket.headers, redis_conn), installation_id)
    if denial:
        _record_websocket_security_event(
            "denied",
            installation_id=installation_id,
            client_ip=client_ip,
            reason=denial,
        )
        await websocket.close(code=1008)
        return
    if not _is_registered_installation(redis_conn, installation_id):
        _record_websocket_security_event(
            "denied",
            installation_id=installation_id,
            client_ip=client_ip,
            reason="installation_not_registered",
        )
        await websocket.close(code=1008)
        return
    acquired = await WEBSOCKET_LIMITER.try_acquire(installation_id)
    if not acquired:
        _record_websocket_security_event(
            "denied",
            installation_id=installation_id,
            client_ip=client_ip,
            reason="connection_limit_exceeded",
        )
        await websocket.close(code=_websocket_close_try_again_later())
        return
    try:
        await websocket.accept()
        async with WATCHERS_LOCK:
            WATCHERS.setdefault(installation_id, []).append(websocket)
        _record_websocket_event(
            "opened",
            installation_id=installation_id,
            client_ip=client_ip,
        )

        key = _metrics_key(installation_id)

        def read_metrics() -> dict:
            try:
                raw = redis_conn.get(key)
            except RedisError:
                return {"error": "Redis service unavailable"}
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except JSONDecodeError:
                return {"error": "corrupted metrics data"}

        # Initial snapshot
        if not await _send_limited_json(
            websocket, read_metrics(), installation_id=installation_id
        ):
            return

        # Periodic updates
        while True:
            await asyncio.sleep(WEBSOCKET_METRICS_INTERVAL)
            if not await _send_limited_json(
                websocket, read_metrics(), installation_id=installation_id
            ):
                break
    except WebSocketDisconnect:
        logger.debug(
            "Metrics websocket disconnected for installation %s", installation_id
        )
    finally:
        # best-effort cleanup
        async with WATCHERS_LOCK:
            lst = WATCHERS.get(installation_id)
            if lst and websocket in lst:
                WATCHERS[installation_id] = [ws for ws in lst if ws is not websocket]
                lst = WATCHERS[installation_id]
                if not lst:
                    WATCHERS.pop(installation_id, None)
        await WEBSOCKET_LIMITER.release(installation_id)
        _record_websocket_event(
            "closed",
            installation_id=installation_id,
            client_ip=client_ip,
        )
