"""FastAPI service for hosted monitoring across installations."""

import asyncio
import json
from json import JSONDecodeError
from typing import Any, Dict, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

app = FastAPI()

# Redis-backed storage of metrics per installation with TTLs
METRICS_TTL = 60
REGISTRATION_TTL = 86400  # 24h registration marker by default
WATCHERS: Dict[str, List[WebSocket]] = {}

WEBSOCKET_METRICS_INTERVAL = 5


@app.post("/register")
async def register_installation(payload: Dict[str, Any]):
    installation_id = payload.get("installation_id")
    if not installation_id:
        return JSONResponse({"error": "installation_id required"}, status_code=400)
    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "storage unavailable"}, status_code=500)
    # Mark the installation as registered with its own, longer-lived key
    registration_key = tenant_key(f"cloud:install:registered:{installation_id}")
    redis_conn.set(registration_key, json.dumps({"registered": True}), ex=REGISTRATION_TTL)
    return {"status": "registered", "installation_id": installation_id}


@app.post("/metrics")
async def push_metrics(payload: Dict[str, Any]):
    installation_id = payload.get("installation_id")
    metrics = payload.get("metrics")
    if not installation_id or not isinstance(metrics, dict):
        return JSONResponse({"error": "invalid payload"}, status_code=400)
    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "storage unavailable"}, status_code=500)
    key = tenant_key(f"cloud:install:{installation_id}")
    redis_conn.set(key, json.dumps(metrics), ex=METRICS_TTL)
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
    raw = redis_conn.get(key)
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
            raw = redis_conn.get(key)
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
