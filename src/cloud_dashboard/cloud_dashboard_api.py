"""FastAPI service for hosted monitoring across installations."""

import asyncio
import json
from typing import Any, Dict, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

app = FastAPI()

# Redis-backed storage of metrics per installation with TTL
METRICS_TTL = 60
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
    key = tenant_key(f"cloud:install:{installation_id}")
    registration_key = tenant_key(f"cloud:install:registered:{installation_id}")
    redis_conn.set(registration_key, json.dumps({"registered": True}), ex=REGISTRATION_TTL)
    return {"status": "registered", "installation_id": installation_id}


@app.post("/push")
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
            pass
    return {"status": "ok"}


@app.get("/metrics/{installation_id}")
async def get_metrics(installation_id: str):
    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "storage unavailable"}, status_code=500)
    key = tenant_key(f"cloud:install:{installation_id}")
    raw = redis_conn.get(key)
    return json.loads(raw) if raw else {}


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
        # Send initial metrics if available
        key = tenant_key(f"cloud:install:{installation_id}")
        raw = redis_conn.get(key)
        metrics = json.loads(raw) if raw else {}
        await websocket.send_json(metrics)
        while True:
            await asyncio.sleep(WEBSOCKET_METRICS_INTERVAL)
            raw = redis_conn.get(key)
            metrics = json.loads(raw) if raw else {}
            await websocket.send_json(metrics)
    except WebSocketDisconnect:
        pass
    finally:
        WATCHERS.get(installation_id, []).remove(websocket)
