# src/admin_ui/admin_ui.py
"""FastAPI admin interface for monitoring and management.

This module exposes a small FastAPI application used by the defense stack's
administrators. It provides endpoints for viewing Prometheus metrics, managing
IP block lists stored in Redis and adjusting basic settings. The application is
designed to be run as a standalone service or within Docker.
"""
import asyncio
import json
import logging
import os
import secrets
import time
from base64 import b64decode
from collections import deque
from uuid import uuid4

import pyotp
from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticationCredential,
    PublicKeyCredentialDescriptor,
    RegistrationCredential,
)

from src.shared.audit import log_event
from src.shared.config import CONFIG, get_secret, tenant_key
from src.shared.metrics import get_metrics
from src.shared.redis_client import get_redis_connection

logger = logging.getLogger(__name__)

# Flag to indicate if metrics collection is actually available. Tests patch this
# to simulate metrics being disabled.
METRICS_TRULY_AVAILABLE = True

# Interval in seconds between metric pushes over WebSocket
WEBSOCKET_METRICS_INTERVAL = 5

# Path to the block events log file used for statistics
BLOCK_LOG_FILE = os.getenv("BLOCK_LOG_FILE", "/app/logs/block_events.log")


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


def _load_recent_block_events(limit: int = 5) -> list[dict]:
    """Load the most recent block events from the log file."""
    if not os.path.exists(BLOCK_LOG_FILE):
        return []
    events: list[dict] = []
    try:
        with open(BLOCK_LOG_FILE, "r", encoding="utf-8") as f:
            lines = deque(f, maxlen=limit)
        for line in lines:
            try:
                data = json.loads(line)
                events.append(
                    {
                        "timestamp": data.get("timestamp"),
                        "ip": data.get("ip_address"),
                        "reason": data.get("reason"),
                    }
                )
            except Exception as exc:
                logger.error("Failed to parse block event line: %s", line, exc_info=exc)
                continue
    except Exception as exc:
        logger.error("Error reading block events log", exc_info=exc)
        return []
    return events


# Exposed for tests so they can patch the behaviour
_load_recent_block_events_func = _load_recent_block_events


def _discover_plugins() -> list[str]:
    """Return a list of available plugin module names."""
    plugin_dir = os.getenv("PLUGIN_DIR", "/app/plugins")
    names: list[str] = []
    if os.path.isdir(plugin_dir):
        for fn in os.listdir(plugin_dir):
            if fn.endswith(".py") and not fn.startswith("_"):
                names.append(fn[:-3])
    return sorted(names)


BASE_DIR = os.path.dirname(__file__)


def _get_allowed_origins() -> list[str]:
    """Return a validated list of CORS origins for the Admin UI.

    The value is read when the application starts. Changing the
    ``ADMIN_UI_CORS_ORIGINS`` environment variable requires restarting the
    service to take effect.
    """
    raw = os.getenv("ADMIN_UI_CORS_ORIGINS", "http://localhost")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if "*" in origins:
        raise ValueError(
            "ADMIN_UI_CORS_ORIGINS cannot include '*' when allow_credentials is True"
        )
    return origins


app = FastAPI()
# Origin configuration is evaluated at startup and requires an application
# restart to change.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_CSP = "default-src 'self'"


@app.middleware("http")
async def csp_header(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault(
        "Content-Security-Policy", os.getenv("ADMIN_UI_CSP", DEFAULT_CSP)
    )
    return response


templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount(
    "/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static"
)

# Editable runtime settings managed via the Admin UI
RUNTIME_SETTINGS = {
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
    "ESCALATION_ENDPOINT": CONFIG.ESCALATION_ENDPOINT,
    "ALLOWED_PLUGINS": os.getenv("ALLOWED_PLUGINS", "ua_blocker"),
}

ADMIN_UI_ROLE = os.getenv("ADMIN_UI_ROLE", "admin")

security = HTTPBasic()

# Fallback in-memory stores for WebAuthn when Redis is unavailable
WEBAUTHN_CREDENTIALS: dict[str, dict] = {}
WEBAUTHN_CHALLENGES: dict[str, bytes] = {}
VALID_WEBAUTHN_TOKENS: dict[str, tuple[str, float]] = {}
WEBAUTHN_TOKEN_TTL = 300

RP_ID = os.getenv("WEBAUTHN_RP_ID", "localhost")
ORIGIN = os.getenv("WEBAUTHN_ORIGIN", "http://localhost")


def _cred_key(user: str) -> str:
    return tenant_key(f"webauthn:cred:{user}")


def _token_key(token: str) -> str:
    return tenant_key(f"webauthn:token:{token}")


def _store_webauthn_credential(user: str, cred: dict) -> None:
    redis_conn = get_redis_connection()
    if redis_conn:
        redis_conn.set(_cred_key(user), json.dumps(cred))
    else:
        WEBAUTHN_CREDENTIALS[user] = cred


def _load_webauthn_credential(user: str) -> dict | None:
    redis_conn = get_redis_connection()
    if redis_conn:
        raw = redis_conn.get(_cred_key(user))
        return json.loads(raw) if raw else None
    return WEBAUTHN_CREDENTIALS.get(user)


def _store_webauthn_token(token: str, user: str) -> None:
    redis_conn = get_redis_connection()
    if redis_conn:
        redis_conn.set(_token_key(token), user, ex=WEBAUTHN_TOKEN_TTL)
    else:
        VALID_WEBAUTHN_TOKENS[token] = (user, time.time() + WEBAUTHN_TOKEN_TTL)


def _consume_webauthn_token(token: str | None) -> str | None:
    if not token:
        return None
    redis_conn = get_redis_connection()
    if redis_conn:
        key = _token_key(token)
        username = redis_conn.get(key)
        if username:
            redis_conn.delete(key)
            return username
        return None
    user_exp = VALID_WEBAUTHN_TOKENS.get(token)
    if not user_exp:
        return None
    user, exp = user_exp
    if exp < time.time():
        VALID_WEBAUTHN_TOKENS.pop(token, None)
        return None
    VALID_WEBAUTHN_TOKENS.pop(token, None)
    return user


def require_auth(
    credentials: HTTPBasicCredentials = Depends(security),
    x_2fa_code: str | None = Header(None, alias="X-2FA-Code"),
    x_2fa_token: str | None = Header(None, alias="X-2FA-Token"),
) -> str:
    """Validate HTTP Basic credentials and optional 2FA."""
    username = os.getenv("ADMIN_UI_USERNAME", "admin")
    try:
        password = os.environ["ADMIN_UI_PASSWORD"]
    except KeyError as exc:  # pragma: no cover - defensive
        raise RuntimeError(
            "ADMIN_UI_PASSWORD environment variable must be set",
        ) from exc
    valid = secrets.compare_digest(
        credentials.username,
        username,
    ) and secrets.compare_digest(credentials.password, password)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"},
        )

    token_user = _consume_webauthn_token(x_2fa_token)
    if token_user:
        if token_user != credentials.username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid 2FA token",
                headers={"WWW-Authenticate": "Basic"},
            )
        return credentials.username

    totp_secret = os.getenv("ADMIN_UI_2FA_SECRET") or get_secret(
        "ADMIN_UI_2FA_SECRET_FILE",
    )
    if totp_secret:
        if not x_2fa_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="2FA code required",
                headers={"WWW-Authenticate": "Basic"},
            )
        totp = pyotp.TOTP(totp_secret)
        if not totp.verify(x_2fa_code, valid_window=1):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid 2FA code",
                headers={"WWW-Authenticate": "Basic"},
            )
        return credentials.username

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="2FA token required",
        headers={"WWW-Authenticate": "Basic"},
    )


def require_admin(user: str = Depends(require_auth)) -> str:
    """Ensure the authenticated user has admin privileges."""
    if ADMIN_UI_ROLE != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


@pass_context
def _jinja_url_for(context, name: str, **path_params) -> str:
    """Support Flask-style 'filename' parameter for static files."""
    request: Request = context["request"]
    if "filename" in path_params:
        path_params["path"] = path_params.pop("filename")
    return request.url_for(name, **path_params)


templates.env.globals["url_for"] = _jinja_url_for


@app.post("/webauthn/register/begin")
async def webauthn_register_begin(user: str = Depends(require_auth)):
    """Begin WebAuthn registration and return options."""
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name="AI Scraping Defense",
        user_id=user.encode(),
        user_name=user,
    )
    WEBAUTHN_CHALLENGES[user] = options.challenge
    return JSONResponse(json.loads(options_to_json(options)))


@app.post("/webauthn/register/complete")
async def webauthn_register_complete(data: dict, user: str = Depends(require_auth)):
    """Complete WebAuthn registration."""
    credential = RegistrationCredential.parse_raw(json.dumps(data["credential"]))
    verification = verify_registration_response(
        credential=credential,
        expected_challenge=WEBAUTHN_CHALLENGES.pop(user),
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
    )
    _store_webauthn_credential(
        user,
        {
            "credential_id": verification.credential_id,
            "public_key": verification.credential_public_key,
            "sign_count": verification.sign_count,
        },
    )
    return JSONResponse({"status": "ok"})


@app.post("/webauthn/login/begin")
async def webauthn_login_begin(data: dict):
    """Begin WebAuthn authentication and return options."""
    username = data.get("username")
    if not isinstance(username, str) or not username:
        raise HTTPException(status_code=400, detail="Invalid or missing username")
    cred = _load_webauthn_credential(username)
    if not cred:
        raise HTTPException(status_code=400, detail="Unknown user")
    descriptor = PublicKeyCredentialDescriptor(id=cred["credential_id"])
    options = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=[descriptor],
    )
    WEBAUTHN_CHALLENGES[username] = options.challenge
    return JSONResponse(json.loads(options_to_json(options)))


@app.post("/webauthn/login/complete")
async def webauthn_login_complete(data: dict):
    """Complete WebAuthn authentication and return a token."""
    username = data.get("username")
    if not isinstance(username, str) or not username:
        raise HTTPException(status_code=400, detail="Invalid or missing username")
    cred = _load_webauthn_credential(username)
    if not cred:
        raise HTTPException(status_code=400, detail="Unknown user")
    credential = AuthenticationCredential.parse_raw(json.dumps(data["credential"]))
    verification = verify_authentication_response(
        credential=credential,
        expected_challenge=WEBAUTHN_CHALLENGES.pop(username),
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
        credential_public_key=cred["public_key"],
        credential_current_sign_count=cred["sign_count"],
    )
    cred["sign_count"] = verification.new_sign_count
    _store_webauthn_credential(username, cred)
    token = uuid4().hex
    _store_webauthn_token(token, username)
    return JSONResponse({"token": token})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: str = Depends(require_auth)):
    """Serves the main dashboard HTML page."""
    return templates.TemplateResponse("index.html", {"request": request, "user": user})


@app.get("/metrics")
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


@app.websocket("/ws/metrics")
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
                        HTTPBasicCredentials(username=username, password=password),
                        x_2fa_code=x_2fa_code,
                        x_2fa_token=x_2fa_token,
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


@app.get("/block_stats")
async def block_stats(user: str = Depends(require_auth)):
    """Return blocklist counts and bot detection statistics."""
    metrics_dict = {}
    try:
        metrics_dict = _get_metrics_dict_func()
    except Exception as exc:
        logger.error("Failed to load metrics", exc_info=exc)
        metrics_dict = {}
    total_bots = sum(
        float(v) for k, v in metrics_dict.items() if k.startswith("bots_detected")
    )
    total_humans = sum(
        float(v) for k, v in metrics_dict.items() if k.startswith("humans_detected")
    )

    redis_conn = get_redis_connection()
    blocked_ips = set()
    temp_block_count = 0
    if redis_conn:
        try:
            blocked_ips = redis_conn.smembers(tenant_key("blocklist")) or set()
            temp_block_count = len(redis_conn.keys(tenant_key("blocklist:ip:*")))
        except Exception as exc:
            logger.error("Error loading blocklist from redis", exc_info=exc)

    recent_events = _load_recent_block_events_func(5)
    return JSONResponse(
        {
            "blocked_ip_count": len(blocked_ips),
            "temporary_block_count": temp_block_count,
            "total_bots_detected": total_bots,
            "total_humans_detected": total_humans,
            "recent_block_events": recent_events,
        }
    )


@app.get("/blocklist")
async def get_blocklist(user: str = Depends(require_auth)):
    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)

    blocklist_set = redis_conn.smembers(tenant_key("blocklist"))
    if asyncio.iscoroutine(blocklist_set):
        blocklist_set = await blocklist_set

    if blocklist_set and isinstance(blocklist_set, (set, list)):
        return JSONResponse(list(blocklist_set))
    else:
        return JSONResponse([])


@app.post("/block")
async def block_ip(request: Request, user: str = Depends(require_admin)):
    json_data = await request.json()
    if not json_data:
        return JSONResponse(
            {"error": "Invalid request, missing JSON body"}, status_code=400
        )

    ip = json_data.get("ip")
    if not ip:
        return JSONResponse({"error": "Invalid request, missing ip"}, status_code=400)

    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)

    redis_conn.sadd(tenant_key("blocklist"), ip)
    log_event(user, "block_ip", {"ip": ip})
    return JSONResponse({"status": "success", "ip": ip})


@app.post("/unblock")
async def unblock_ip(request: Request, user: str = Depends(require_admin)):
    json_data = await request.json()
    if not json_data:
        return JSONResponse(
            {"error": "Invalid request, missing JSON body"}, status_code=400
        )

    ip = json_data.get("ip")
    if not ip:
        return JSONResponse({"error": "Invalid request, missing ip"}, status_code=400)

    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse({"error": "Redis service unavailable"}, status_code=503)

    redis_conn.srem(tenant_key("blocklist"), ip)
    log_event(user, "unblock_ip", {"ip": ip})
    return JSONResponse({"status": "success", "ip": ip})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    csrf_token: str | None = Cookie(None),
    user: str = Depends(require_auth),
):
    """Renders the system settings page with a CSRF token."""
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(16)
    current_settings = {
        "Model URI": os.getenv("MODEL_URI", "Not Set"),
        "LOG_LEVEL": RUNTIME_SETTINGS["LOG_LEVEL"],
        "ESCALATION_ENDPOINT": RUNTIME_SETTINGS["ESCALATION_ENDPOINT"],
    }
    response = templates.TemplateResponse(
        "settings.html",
        {"request": request, "settings": current_settings, "csrf_token": csrf_token},
    )
    response.set_cookie(
        "csrf_token",
        csrf_token,
        httponly=True,
        secure=True,
        samesite="Strict",
    )
    return response


@app.post("/settings", response_class=HTMLResponse)
async def update_settings(
    request: Request,
    csrf_token: str | None = Cookie(None),
    user: str = Depends(require_admin),
):
    """Update editable settings from form data, validating the CSRF token."""
    form = await request.form()
    if not csrf_token or form.get("csrf_token") != csrf_token:
        return HTMLResponse("Invalid CSRF token", status_code=400)
    log_level = form.get("LOG_LEVEL")
    escalation_endpoint = form.get("ESCALATION_ENDPOINT")

    if log_level:
        RUNTIME_SETTINGS["LOG_LEVEL"] = log_level
        os.environ["LOG_LEVEL"] = log_level
    if escalation_endpoint:
        RUNTIME_SETTINGS["ESCALATION_ENDPOINT"] = escalation_endpoint
        os.environ["ESCALATION_ENDPOINT"] = escalation_endpoint

    log_event(
        user,
        "update_settings",
        {"log_level": log_level, "endpoint": escalation_endpoint},
    )

    current_settings = {
        "Model URI": os.getenv("MODEL_URI", "Not Set"),
        "LOG_LEVEL": RUNTIME_SETTINGS["LOG_LEVEL"],
        "ESCALATION_ENDPOINT": RUNTIME_SETTINGS["ESCALATION_ENDPOINT"],
    }
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "settings": current_settings, "updated": True},
    )


@app.get("/logs", response_class=HTMLResponse)
async def view_logs(request: Request, user: str = Depends(require_auth)):
    """Display recent block events."""
    events = _load_recent_block_events_func(50)
    return templates.TemplateResponse(
        "logs.html", {"request": request, "events": events}
    )


@app.get("/plugins", response_class=HTMLResponse)
async def plugins_page(request: Request, user: str = Depends(require_auth)):
    """Show available plugins and which are enabled."""
    available = _discover_plugins()
    enabled = (
        RUNTIME_SETTINGS["ALLOWED_PLUGINS"].split(",")
        if RUNTIME_SETTINGS["ALLOWED_PLUGINS"]
        else []
    )
    return templates.TemplateResponse(
        "plugins.html",
        {"request": request, "available": available, "enabled": enabled},
    )


@app.post("/plugins")
async def update_plugins(request: Request, user: str = Depends(require_admin)):
    """Update enabled plugins and notify the escalation engine."""
    form = await request.form()
    selected = form.getlist("plugins")
    allowed = ",".join(selected)
    RUNTIME_SETTINGS["ALLOWED_PLUGINS"] = allowed
    os.environ["ALLOWED_PLUGINS"] = allowed
    try:
        import httpx

        headers = {}
        if CONFIG.ESCALATION_API_KEY:
            headers["X-API-Key"] = CONFIG.ESCALATION_API_KEY
        httpx.post(
            f"{CONFIG.ESCALATION_ENGINE_URL}/admin/reload_plugins",
            json={"allowed_plugins": selected},
            headers=headers,
            timeout=5.0,
        )
    except Exception as exc:
        logger.error("Failed to notify escalation engine", exc_info=exc)
    log_event(user, "update_plugins", {"plugins": selected})
    return RedirectResponse("/plugins", status_code=302)


if __name__ == "__main__":
    import uvicorn

    # Bind to localhost by default to avoid exposing the service on all interfaces
    host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.getenv("ADMIN_UI_PORT", 5002))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    uvicorn.run("src.admin_ui.admin_ui:app", host=host, port=port, log_level=log_level)
