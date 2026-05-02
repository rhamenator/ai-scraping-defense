"""FastAPI service for hosted monitoring across installations."""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
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
                pass


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


@app.post("/register")
async def register_installation(payload: Dict[str, Any], request: Request):
    if API_KEY and not is_api_key_valid(request.headers.get("X-API-Key"), API_KEY):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    installation_id = _validate_installation_id(payload.get("installation_id"))
    if not installation_id:
        return JSONResponse({"error": "installation_id required"}, status_code=400)

    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "storage unavailable"}, status_code=500)
    # Mark the installation as registered with its own, longer-lived key
    registration_key = tenant_key(f"cloud:install:registered:{installation_id}")
    try:
        with trace_span(
            "cloud_dashboard.register_installation",
            attributes={"installation_id": installation_id},
        ):
            redis_conn.set(
                registration_key,
                json.dumps({"registered": True}),
                ex=REGISTRATION_TTL,
            )
    except RedisError:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)
    return {"status": "registered", "installation_id": installation_id}


@app.post("/metrics")
async def push_metrics(payload: Dict[str, Any], request: Request):
    if API_KEY and not is_api_key_valid(request.headers.get("X-API-Key"), API_KEY):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    installation_id = _validate_installation_id(payload.get("installation_id"))
    metrics = payload.get("metrics")
    if not installation_id or not _validate_metrics(metrics):
        return JSONResponse({"error": "invalid payload"}, status_code=400)

    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "storage unavailable"}, status_code=500)
    key = tenant_key(f"cloud:install:{installation_id}")
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
    if API_KEY and not is_api_key_valid(request.headers.get("X-API-Key"), API_KEY):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    installation_id = _validate_installation_id(installation_id)
    if not installation_id:
        return JSONResponse({"error": "invalid installation_id"}, status_code=400)
    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "storage unavailable"}, status_code=500)
    key = tenant_key(f"cloud:install:{installation_id}")
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
    if API_KEY and not is_api_key_valid(websocket.headers.get("X-API-Key"), API_KEY):
        _record_websocket_security_event(
            "denied",
            installation_id=installation_id,
            client_ip=client_ip,
            reason="api_key_invalid",
        )
        await websocket.close(code=1008)
        return
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

        key = tenant_key(f"cloud:install:{installation_id}")

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
        pass
    finally:
        # best-effort cleanup
        async with WATCHERS_LOCK:
            lst = WATCHERS.get(installation_id)
            if lst and websocket in lst:
                try:
                    lst.remove(websocket)
                except ValueError:
                    pass
                if not lst:
                    WATCHERS.pop(installation_id, None)
        await WEBSOCKET_LIMITER.release(installation_id)
        _record_websocket_event(
            "closed",
            installation_id=installation_id,
            client_ip=client_ip,
        )
