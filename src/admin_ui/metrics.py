import asyncio
import json
import logging
import os
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

from src.shared.audit import log_event
from src.shared.metrics import OPERATIONAL_EVENTS, SECURITY_EVENTS
from src.shared.observability import WebSocketConnectionLimiter

from .auth import _require_auth_core, require_auth
from .metrics_admin_ui import get_metrics

logger = logging.getLogger(__name__)

METRICS_TRULY_AVAILABLE = True
WEBSOCKET_METRICS_INTERVAL = 5
WEBSOCKET_MAX_CONNECTIONS = int(os.getenv("ADMIN_UI_METRICS_WS_MAX_CONNECTIONS", "5"))
WEBSOCKET_MAX_MESSAGE_BYTES = int(
    os.getenv("ADMIN_UI_METRICS_WS_MAX_MESSAGE_BYTES", "65536")
)
SECURITY_KPI_PREFIXES = {
    "security_events_total": "security_events_total",
    "errors_total": "errors_total",
    "login_attempts_total": "login_attempts_total",
    "community_reports_attempted_total": "community_reports_attempted_total",
}

router = APIRouter()
WEBSOCKET_LIMITER = WebSocketConnectionLimiter(max_total=WEBSOCKET_MAX_CONNECTIONS)


def _websocket_close_try_again_later() -> int:
    return getattr(status, "WS_1013_TRY_AGAIN_LATER", 1013)


def _client_ip(websocket: WebSocket) -> str:
    client = websocket.client
    return client.host if client and client.host else "unknown"


def _record_websocket_event(action: str, **details) -> None:
    OPERATIONAL_EVENTS.labels(event_type=f"admin_ui_metrics_ws_{action}").inc()
    log_event("admin_ui", f"admin_ui_metrics_websocket_{action}", details)


def _record_websocket_security_event(action: str, **details) -> None:
    SECURITY_EVENTS.labels(event_type=f"admin_ui_metrics_ws_{action}").inc()
    log_event("admin_ui", f"admin_ui_metrics_websocket_{action}", details)


async def _send_limited_json(websocket: WebSocket, payload: dict) -> bool:
    encoded = json.dumps(payload, default=str).encode("utf-8")
    if WEBSOCKET_MAX_MESSAGE_BYTES and len(encoded) > WEBSOCKET_MAX_MESSAGE_BYTES:
        _record_websocket_security_event(
            "payload_too_large",
            client_ip=_client_ip(websocket),
            payload_bytes=len(encoded),
            max_bytes=WEBSOCKET_MAX_MESSAGE_BYTES,
        )
        await websocket.send_json({"error": "Metrics payload too large"})
        await websocket.close(code=_websocket_close_try_again_later())
        return False
    await websocket.send_json(payload)
    return True


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


def _sum_metrics(metrics_dict: dict, prefix: str) -> float:
    return sum(value for key, value in metrics_dict.items() if key.startswith(prefix))


def get_security_kpis() -> dict[str, float]:
    """Return a summary of security KPI counters derived from metrics."""
    metrics_dict = _get_metrics_dict_func()
    return {
        label: _sum_metrics(metrics_dict, prefix)
        for label, prefix in SECURITY_KPI_PREFIXES.items()
    }


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
    client_ip = _client_ip(websocket)
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
                    _require_auth_core(
                        request=None,
                        response=None,
                        credentials=HTTPBasicCredentials(
                            username=username, password=password
                        ),
                        x_2fa_code=x_2fa_code,
                        x_2fa_token=x_2fa_token,
                        x_2fa_backup_code=None,
                        client_ip=client_ip,
                    )
                except HTTPException:
                    _record_websocket_security_event(
                        "denied",
                        client_ip=client_ip,
                        reason="authentication_failed",
                    )
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
        except Exception as exc:
            logger.error("Error during websocket auth", exc_info=exc)
            _record_websocket_security_event(
                "denied",
                client_ip=client_ip,
                reason="invalid_authorization_header",
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    else:
        _record_websocket_security_event(
            "denied",
            client_ip=client_ip,
            reason="missing_authorization_header",
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    acquired = await WEBSOCKET_LIMITER.try_acquire()
    if not acquired:
        _record_websocket_security_event(
            "denied",
            client_ip=client_ip,
            reason="connection_limit_exceeded",
        )
        await websocket.close(code=_websocket_close_try_again_later())
        return
    try:
        await websocket.accept()
        _record_websocket_event("opened", client_ip=client_ip)

        if not METRICS_TRULY_AVAILABLE:
            await _send_limited_json(
                websocket, {"error": "Metrics module not available"}
            )
            await websocket.close()
            return

        while True:
            try:
                metrics_dict = _get_metrics_dict_func()
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "An error occurred in the websocket metrics endpoint",
                    exc_info=exc,
                )
                await _send_limited_json(
                    websocket, {"error": "An internal error occurred"}
                )
                await websocket.close()
                break

            if not await _send_limited_json(websocket, metrics_dict):
                break

            if isinstance(metrics_dict, dict) and metrics_dict.get("error"):
                await websocket.close()
                break

            try:
                await asyncio.sleep(WEBSOCKET_METRICS_INTERVAL)
            except asyncio.CancelledError:  # pragma: no cover - defensive
                break
    except WebSocketDisconnect:  # pragma: no cover - normal disconnect
        pass
    finally:
        await WEBSOCKET_LIMITER.release()
        _record_websocket_event("closed", client_ip=client_ip)
