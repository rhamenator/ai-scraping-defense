import asyncio
import logging
from base64 import b64decode

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasicCredentials

from src.shared.metrics import get_metrics

from .auth import require_auth

logger = logging.getLogger(__name__)

METRICS_TRULY_AVAILABLE = True
WEBSOCKET_METRICS_INTERVAL = 5

router = APIRouter()


def _parse_prometheus_metrics(text: str) -> dict:
    """Convert Prometheus text format into a dictionary."""
    metrics: dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name, value = parts[0], parts[-1]
        try:
            metrics[name] = float(value)
        except ValueError:
            continue
    return metrics


def _get_metrics_dict() -> dict:
    raw = get_metrics()
    if isinstance(raw, bytes):
        raw = raw.decode()
    return _parse_prometheus_metrics(raw)


# Exposed for tests so they can patch the behaviour
_get_metrics_dict_func = _get_metrics_dict


@router.get("/metrics")
async def metrics_endpoint(user: str = Depends(require_auth)):
    """Return metrics in JSON form for the admin dashboard."""
    if not METRICS_TRULY_AVAILABLE:
        return JSONResponse({"error": "Metrics module not available"}, status_code=503)

    try:
        metrics_dict = _get_metrics_dict_func()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("An error occurred in the metrics endpoint", exc_info=exc)
        return JSONResponse({"error": "An internal error occurred"}, status_code=500)

    if isinstance(metrics_dict, dict) and metrics_dict.get("error"):
        return JSONResponse(metrics_dict, status_code=500)

    return JSONResponse(metrics_dict, status_code=200)


@router.websocket("/ws/metrics")
async def metrics_websocket(websocket: WebSocket):
    """Stream metrics to the client over a WebSocket connection."""
    auth = websocket.headers.get("Authorization")
    if auth:
        try:
            scheme, data = auth.split(" ", 1)
            if scheme.lower() == "basic":
                decoded = b64decode(data).decode()
                username, password = decoded.split(":", 1)
                x_2fa_code = websocket.headers.get("X-2FA-Code")
                x_2fa_token = websocket.headers.get("X-2FA-Token")
                try:
                    require_auth(
                        credentials=HTTPBasicCredentials(
                            username=username, password=password
                        ),
                        x_2fa_code=x_2fa_code,
                        x_2fa_token=x_2fa_token,
                        client_ip=websocket.client.host,
                    )
                except HTTPException:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
        except Exception as exc:
            logger.error("Error during websocket auth", exc_info=exc)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    else:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()

    if not METRICS_TRULY_AVAILABLE:
        await websocket.send_json({"error": "Metrics module not available"})
        await websocket.close()
        return

    try:
        while True:
            try:
                metrics_dict = _get_metrics_dict_func()
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "An error occurred in the websocket metrics endpoint",
                    exc_info=exc,
                )
                await websocket.send_json({"error": "An internal error occurred"})
                await websocket.close()
                break

            await websocket.send_json(metrics_dict)

            if isinstance(metrics_dict, dict) and metrics_dict.get("error"):
                await websocket.close()
                break

            try:
                await asyncio.sleep(WEBSOCKET_METRICS_INTERVAL)
            except asyncio.CancelledError:  # pragma: no cover - defensive
                break
    except WebSocketDisconnect:  # pragma: no cover - normal disconnect
        pass
