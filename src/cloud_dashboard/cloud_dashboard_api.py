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
from src.shared.config import tenant_key
from src.shared.middleware import create_app
from src.shared.observability import (
    HealthCheckResult,
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
    for ws in sockets:
        try:
            await ws.send_json(metrics)
        except Exception as e:
            # best-effort fanout
            logger.warning(f"WebSocket send_json failed during metrics fanout: {e}")
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
    if API_KEY and not is_api_key_valid(websocket.headers.get("X-API-Key"), API_KEY):
        await websocket.close(code=1008)
        return
    if not _validate_installation_id(installation_id):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    async with WATCHERS_LOCK:
        WATCHERS.setdefault(installation_id, []).append(websocket)
    try:
        redis_conn = get_redis_connection()
        if not redis_conn:
            await websocket.send_json({"error": "storage unavailable"})
            await websocket.close()
            return

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
        await websocket.send_json(read_metrics())

        # Periodic updates
        while True:
            await asyncio.sleep(WEBSOCKET_METRICS_INTERVAL)
            await websocket.send_json(read_metrics())
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
