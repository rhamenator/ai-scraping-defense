"""FastAPI service for hosted monitoring across installations."""
from typing import Dict, Any, List
import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

app = FastAPI()

# In-memory storage of metrics per installation
INSTALLATIONS: Dict[str, Dict[str, Any]] = {}
WATCHERS: Dict[str, List[WebSocket]] = {}

WEBSOCKET_METRICS_INTERVAL = 5


@app.post("/register")
async def register_installation(payload: Dict[str, Any]):
    installation_id = payload.get("installation_id")
    if not installation_id:
        return JSONResponse({"error": "installation_id required"}, status_code=400)
    INSTALLATIONS.setdefault(installation_id, {"metrics": {}})
    return {"status": "registered", "installation_id": installation_id}


@app.post("/push")
async def push_metrics(payload: Dict[str, Any]):
    installation_id = payload.get("installation_id")
    metrics = payload.get("metrics")
    if not installation_id or not isinstance(metrics, dict):
        return JSONResponse({"error": "invalid payload"}, status_code=400)
    entry = INSTALLATIONS.setdefault(installation_id, {"metrics": {}})
    entry["metrics"] = metrics
    for ws in list(WATCHERS.get(installation_id, [])):
        try:
            await ws.send_json(metrics)
        except Exception:
            pass
    return {"status": "ok"}


@app.get("/metrics/{installation_id}")
async def get_metrics(installation_id: str):
    return INSTALLATIONS.get(installation_id, {}).get("metrics", {})


@app.websocket("/ws/{installation_id}")
async def metrics_websocket(websocket: WebSocket, installation_id: str):
    await websocket.accept()
    WATCHERS.setdefault(installation_id, []).append(websocket)
    try:
        # Send initial metrics if available
        metrics = INSTALLATIONS.get(installation_id, {}).get("metrics", {})
        await websocket.send_json(metrics)
        while True:
            await asyncio.sleep(WEBSOCKET_METRICS_INTERVAL)
            metrics = INSTALLATIONS.get(installation_id, {}).get("metrics", {})
            await websocket.send_json(metrics)
    except WebSocketDisconnect:
        pass
    finally:
        WATCHERS.get(installation_id, []).remove(websocket)
