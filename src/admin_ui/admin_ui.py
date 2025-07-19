# src/admin_ui/admin_ui.py
"""FastAPI admin interface for monitoring and management.

This module exposes a small FastAPI application used by the defense stack's
administrators. It provides endpoints for viewing Prometheus metrics, managing
IP block lists stored in Redis and adjusting basic settings. The application is
designed to be run as a standalone service or within Docker.
"""
import os
import asyncio
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from jinja2 import pass_context
from src.shared.redis_client import get_redis_connection
from src.shared.metrics import get_metrics
from src.shared.config import CONFIG

# Flag to indicate if metrics collection is actually available. Tests patch this
# to simulate metrics being disabled.
METRICS_TRULY_AVAILABLE = True

# Interval in seconds between metric pushes over WebSocket
WEBSOCKET_METRICS_INTERVAL = 5


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

BASE_DIR = os.path.dirname(__file__)
app = FastAPI()
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Editable runtime settings managed via the Admin UI
RUNTIME_SETTINGS = {
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
    "ESCALATION_ENDPOINT": CONFIG.ESCALATION_ENDPOINT,
}


@pass_context
def _jinja_url_for(context, name: str, **path_params) -> str:
    """Support Flask-style 'filename' parameter for static files."""
    request: Request = context["request"]
    if "filename" in path_params:
        path_params["path"] = path_params.pop("filename")
    return request.url_for(name, **path_params)


templates.env.globals["url_for"] = _jinja_url_for


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serves the main dashboard HTML page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/metrics")
async def metrics_endpoint():
    """Return metrics in JSON form for the admin dashboard."""
    if not METRICS_TRULY_AVAILABLE:
        return JSONResponse({"error": "Metrics module not available"}, status_code=503)

    try:
        metrics_dict = _get_metrics_dict_func()
    except Exception as exc:  # pragma: no cover - defensive
        import logging
        logging.error("An error occurred in the metrics endpoint", exc_info=True)
        return JSONResponse({"error": "An internal error occurred"}, status_code=500)

    if isinstance(metrics_dict, dict) and metrics_dict.get("error"):
        return JSONResponse(metrics_dict, status_code=500)

    return JSONResponse(metrics_dict, status_code=200)


@app.websocket("/ws/metrics")
async def metrics_websocket(websocket: WebSocket):
    """Stream metrics to the client over a WebSocket connection."""
    await websocket.accept()

    if not METRICS_TRULY_AVAILABLE:
        await websocket.send_json({"error": "Metrics module not available"})
        await websocket.close()
        return

    try:
        while True:
            try:
                metrics_dict = _get_metrics_dict_func()
            except Exception:  # pragma: no cover - defensive
                import logging
                logging.error(
                    "An error occurred in the websocket metrics endpoint",
                    exc_info=True,
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


@app.get("/blocklist")
async def get_blocklist():
    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)

    blocklist_set = redis_conn.smembers("blocklist")
    if asyncio.iscoroutine(blocklist_set):
        blocklist_set = await blocklist_set

    if blocklist_set and isinstance(blocklist_set, (set, list)):
        return JSONResponse(list(blocklist_set))
    else:
        return JSONResponse([])


@app.post("/block")
async def block_ip(request: Request):
    json_data = await request.json()
    if not json_data:
        return JSONResponse({"error": "Invalid request, missing JSON body"}, status_code=400)

    ip = json_data.get("ip")
    if not ip:
        return JSONResponse({"error": "Invalid request, missing ip"}, status_code=400)

    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)

    redis_conn.sadd("blocklist", ip)
    return JSONResponse({"status": "success", "ip": ip})


@app.post("/unblock")
async def unblock_ip(request: Request):
    json_data = await request.json()
    if not json_data:
        return JSONResponse({"error": "Invalid request, missing JSON body"}, status_code=400)

    ip = json_data.get("ip")
    if not ip:
        return JSONResponse({"error": "Invalid request, missing ip"}, status_code=400)

    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)

    redis_conn.srem("blocklist", ip)
    return JSONResponse({"status": "success", "ip": ip})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Renders the system settings page."""
    current_settings = {
        "Model URI": os.getenv("MODEL_URI", "Not Set"),
        "LOG_LEVEL": RUNTIME_SETTINGS["LOG_LEVEL"],
        "ESCALATION_ENDPOINT": RUNTIME_SETTINGS["ESCALATION_ENDPOINT"],
    }
    return templates.TemplateResponse(
        "settings.html", {"request": request, "settings": current_settings}
    )


@app.post("/settings", response_class=HTMLResponse)
async def update_settings(request: Request):
    """Update editable settings from form data."""
    form = await request.form()
    log_level = form.get("LOG_LEVEL")
    escalation_endpoint = form.get("ESCALATION_ENDPOINT")

    if log_level:
        RUNTIME_SETTINGS["LOG_LEVEL"] = log_level
        os.environ["LOG_LEVEL"] = log_level
    if escalation_endpoint:
        RUNTIME_SETTINGS["ESCALATION_ENDPOINT"] = escalation_endpoint
        os.environ["ESCALATION_ENDPOINT"] = escalation_endpoint

    current_settings = {
        "Model URI": os.getenv("MODEL_URI", "Not Set"),
        "LOG_LEVEL": RUNTIME_SETTINGS["LOG_LEVEL"],
        "ESCALATION_ENDPOINT": RUNTIME_SETTINGS["ESCALATION_ENDPOINT"],
    }
    return templates.TemplateResponse(
        "settings.html", {"request": request, "settings": current_settings, "updated": True}
    )


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.getenv("ADMIN_UI_PORT", 5002))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    uvicorn.run("src.admin_ui.admin_ui:app", host=host, port=port, log_level=log_level)
