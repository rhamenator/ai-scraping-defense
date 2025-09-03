"""FastAPI service for hosted monitoring across installations."""

import asyncio
import json
import os
from json import JSONDecodeError
from typing import Any, Dict, List

from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from starlette.websockets import WebSocketState

from src.shared.config import tenant_key
from src.shared.middleware import create_app
from src.shared.redis_client import get_redis_connection

app = create_app()

API_KEY = os.getenv("CLOUD_DASHBOARD_API_KEY")

# Redis-backed storage of metrics per installation with TTLs
METRICS_TTL = 60
REGISTRATION_TTL = 86400  # 24h registration marker by default
WATCHERS: Dict[str, List[WebSocket]] = {}

WEBSOCKET_METRICS_INTERVAL = 5
WATCHERS_CLEANUP_INTERVAL = 60


async def _cleanup_stale_watchers() -> None:
    while True:
        await asyncio.sleep(WATCHERS_CLEANUP_INTERVAL)
        for inst_id, sockets in list(WATCHERS.items()):
            WATCHERS[inst_id] = [
                ws
                for ws in sockets
                if ws.client_state == WebSocketState.CONNECTED
                and ws.application_state == WebSocketState.CONNECTED
            ]
            if not WATCHERS[inst_id]:
                WATCHERS.pop(inst_id, None)


@app.on_event("startup")
async def _start_watchers_cleanup() -> None:  # pragma: no cover - background task
    asyncio.create_task(_cleanup_stale_watchers())


@app.post("/register")
async def register_installation(payload: Dict[str, Any], request: Request):
    if API_KEY and request.headers.get("X-API-Key") != API_KEY:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    installation_id = payload.get("installation_id")
    if not installation_id:
        return JSONResponse({"error": "installation_id required"}, status_code=400)

    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "storage unavailable"}, status_code=500)
    # Mark the installation as registered with its own, longer-lived key
    registration_key = tenant_key(f"cloud:install:registered:{installation_id}")
    try:
        redis_conn.set(
            registration_key, json.dumps({"registered": True}), ex=REGISTRATION_TTL
        )
    except RedisError:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)
    return {"status": "registered", "installation_id": installation_id}


@app.post("/metrics")
async def push_metrics(payload: Dict[str, Any], request: Request):
    if API_KEY and request.headers.get("X-API-Key") != API_KEY:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    installation_id = payload.get("installation_id")
    metrics = payload.get("metrics")
    if not installation_id or not isinstance(metrics, dict):
        return JSONResponse({"error": "invalid payload"}, status_code=400)

    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "storage unavailable"}, status_code=500)
    key = tenant_key(f"cloud:install:{installation_id}")
    try:
        redis_conn.set(key, json.dumps(metrics), ex=METRICS_TTL)
    except RedisError:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)
    for ws in list(WATCHERS.get(installation_id, [])):
        try:
            await ws.send_json(metrics)
        except Exception:
            # best-effort fanout
            pass
    return {"status": "ok"}


@app.get("/metrics/{installation_id}")
async def get_metrics(installation_id: str):
    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "storage unavailable"}, status_code=500)
    key = tenant_key(f"cloud:install:{installation_id}")
    try:
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
    await websocket.accept()
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
        lst = WATCHERS.get(installation_id)
        if lst and websocket in lst:
            try:
                lst.remove(websocket)
            except ValueError:
                pass
            if not lst:
                WATCHERS.pop(installation_id, None)
