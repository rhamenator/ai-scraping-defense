# src/admin_ui/admin_ui.py
"""FastAPI admin interface for monitoring and management.

This module assembles the FastAPI application and wires in
submodules that handle authentication, metrics, blocklist
management and WebAuthn support.
"""
import logging
import os
import secrets

from fastapi import Cookie, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context

from src.shared.audit import log_event
from src.shared.config import CONFIG, tenant_key
from src.shared.middleware import create_app
from src.shared.redis_client import get_redis_connection

from . import auth as auth_routes
from . import blocklist, metrics, webauthn
from .auth import require_admin, require_auth

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)

# Editable runtime settings managed via the Admin UI
RUNTIME_SETTINGS_KEY = tenant_key("admin_ui:settings")
DEFAULT_RUNTIME_SETTINGS = {
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
    "ESCALATION_ENDPOINT": CONFIG.ESCALATION_ENDPOINT,
    "ALLOWED_PLUGINS": os.getenv("ALLOWED_PLUGINS", "ua_blocker"),
}

WEBAUTHN_TOKEN_TTL = 300


def _get_runtime_setting(name: str) -> str:
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    value = redis_conn.hget(RUNTIME_SETTINGS_KEY, name)
    if value is None:
        default = DEFAULT_RUNTIME_SETTINGS[name]
        redis_conn.hset(RUNTIME_SETTINGS_KEY, name, default)
        return default
    return value


def _set_runtime_setting(name: str, value: str) -> None:
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    redis_conn.hset(RUNTIME_SETTINGS_KEY, name, value)


def _discover_plugins() -> list[str]:
    """Return a list of available plugin module names."""
    plugin_dir = os.getenv("PLUGIN_DIR", "/app/plugins")
    names: list[str] = []
    if os.path.isdir(plugin_dir):
        for fn in os.listdir(plugin_dir):
            if fn.endswith(".py") and not fn.startswith("_"):
                names.append(fn[:-3])
    return sorted(names)


def _get_allowed_origins() -> list[str]:
    """Return a validated list of CORS origins for the Admin UI."""
    raw = os.getenv("ADMIN_UI_CORS_ORIGINS", "http://localhost")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if "*" in origins:
        raise ValueError(
            "ADMIN_UI_CORS_ORIGINS cannot include '*' when allow_credentials is True"
        )
    return origins


app = create_app()
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


@pass_context
def _jinja_url_for(context, name: str, **path_params) -> str:
    """Support Flask-style 'filename' parameter for static files."""
    request: Request = context["request"]
    if "filename" in path_params:
        path_params["path"] = path_params.pop("filename")
    return request.url_for(name, **path_params)


templates.env.globals["url_for"] = _jinja_url_for

app.mount(
    "/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static"
)
# Include routers from submodules
app.include_router(metrics.router)
app.include_router(blocklist.router)
app.include_router(webauthn.router)
app.include_router(auth_routes.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: str = Depends(require_auth)):
    """Serves the main dashboard HTML page."""
    return templates.TemplateResponse(request, "index.html", {"user": user})


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
        "LOG_LEVEL": _get_runtime_setting("LOG_LEVEL"),
        "ESCALATION_ENDPOINT": _get_runtime_setting("ESCALATION_ENDPOINT"),
    }
    response = templates.TemplateResponse(
        request,
        "settings.html",
        {"settings": current_settings, "csrf_token": csrf_token},
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
        _set_runtime_setting("LOG_LEVEL", log_level)
        os.environ["LOG_LEVEL"] = log_level
    if escalation_endpoint:
        _set_runtime_setting("ESCALATION_ENDPOINT", escalation_endpoint)
        os.environ["ESCALATION_ENDPOINT"] = escalation_endpoint

    log_event(
        user,
        "update_settings",
        {"log_level": log_level, "endpoint": escalation_endpoint},
    )

    current_settings = {
        "Model URI": os.getenv("MODEL_URI", "Not Set"),
        "LOG_LEVEL": _get_runtime_setting("LOG_LEVEL"),
        "ESCALATION_ENDPOINT": _get_runtime_setting("ESCALATION_ENDPOINT"),
    }
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"settings": current_settings, "updated": True},
    )


@app.get("/logs", response_class=HTMLResponse)
async def view_logs(request: Request, user: str = Depends(require_auth)):
    """Display recent block events."""
    events = blocklist._load_recent_block_events_func(50)
    return templates.TemplateResponse(request, "logs.html", {"events": events})


@app.get("/plugins", response_class=HTMLResponse)
async def plugins_page(request: Request, user: str = Depends(require_auth)):
    """Show available plugins and which are enabled."""
    available = _discover_plugins()
    allowed_plugins = _get_runtime_setting("ALLOWED_PLUGINS")
    enabled = allowed_plugins.split(",") if allowed_plugins else []
    return templates.TemplateResponse(
        request,
        "plugins.html",
        {"available": available, "enabled": enabled},
    )


@app.post("/plugins")
async def update_plugins(request: Request, user: str = Depends(require_admin)):
    """Update enabled plugins and notify the escalation engine."""
    form = await request.form()
    selected = form.getlist("plugins")
    allowed = ",".join(selected)
    _set_runtime_setting("ALLOWED_PLUGINS", allowed)
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

    host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.getenv("ADMIN_UI_PORT", 5002))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    uvicorn.run("src.admin_ui.admin_ui:app", host=host, port=port, log_level=log_level)
