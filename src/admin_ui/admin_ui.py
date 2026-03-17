# src/admin_ui/admin_ui.py
"""FastAPI admin interface for monitoring and management.

This module assembles the FastAPI application and wires in
submodules that handle authentication, metrics, blocklist
management and WebAuthn support.
"""
import logging
import os
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import Cookie, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from redis.exceptions import RedisError

from src.shared.audit import log_event
from src.shared.config import CONFIG, tenant_key
from src.shared.middleware import create_app
from src.shared.observability import (
    HealthCheckResult,
    ObservabilitySettings,
    register_health_check,
    trace_span,
)
from src.shared.redis_client import get_redis_connection

from . import auth as auth_routes
from . import blocklist, metrics, webauthn
from .auth import require_admin, require_auth

logger = logging.getLogger(__name__)

CSRF_COOKIE_TTL = int(os.getenv("ADMIN_UI_CSRF_COOKIE_TTL", "3600"))

BASE_DIR = os.path.dirname(__file__)

# Editable runtime settings managed via the Admin UI
RUNTIME_SETTINGS_KEY = tenant_key("admin_ui:settings")
ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
WEBAUTHN_ATTACHMENT_OPTIONS = {"none", "platform", "cross-platform"}


@dataclass(frozen=True)
class EditableSetting:
    key: str
    label: str
    description: str
    input_type: str
    default: str
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecretReferenceSetting:
    label: str
    file_env: str
    vault_env: str


EDITABLE_SETTINGS: tuple[EditableSetting, ...] = (
    EditableSetting(
        key="LOG_LEVEL",
        label="Log Level",
        description="Controls admin UI logging verbosity.",
        input_type="select",
        default=os.getenv("LOG_LEVEL", "INFO"),
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
    ),
    EditableSetting(
        key="ESCALATION_ENDPOINT",
        label="Escalation Engine URL",
        description="Absolute HTTP(S) URL for escalation requests.",
        input_type="text",
        default=CONFIG.ESCALATION_ENDPOINT,
    ),
    EditableSetting(
        key="WEBAUTHN_AUTHENTICATOR_ATTACHMENT",
        label="WebAuthn Authenticator Preference",
        description="Preferred authenticator attachment for admin login.",
        input_type="select",
        default=os.getenv("WEBAUTHN_AUTHENTICATOR_ATTACHMENT", "none"),
        choices=("none", "platform", "cross-platform"),
    ),
    EditableSetting(
        key="RATE_LIMIT_REQUESTS",
        label="Rate Limit Requests",
        description="Maximum requests allowed per rate-limit window.",
        input_type="number",
        default=os.getenv("RATE_LIMIT_REQUESTS", "100"),
    ),
    EditableSetting(
        key="RATE_LIMIT_WINDOW",
        label="Rate Limit Window (seconds)",
        description="Rate-limit window size in seconds.",
        input_type="number",
        default=os.getenv("RATE_LIMIT_WINDOW", "60"),
    ),
    EditableSetting(
        key="MAX_BODY_SIZE",
        label="Max Body Size (bytes)",
        description="Largest request body accepted by shared middleware.",
        input_type="number",
        default=os.getenv("MAX_BODY_SIZE", str(1 * 1024 * 1024)),
    ),
    EditableSetting(
        key="ENABLE_HTTPS",
        label="HTTPS Redirect Enforcement",
        description="Redirect plain HTTP requests to HTTPS in shared middleware.",
        input_type="select",
        default=os.getenv("ENABLE_HTTPS", "false"),
        choices=("true", "false"),
    ),
    EditableSetting(
        key="ALLOWED_PLUGINS",
        label="Allowed Plugins",
        description="Comma-separated plugin allowlist pushed to the escalation engine.",
        input_type="multiselect",
        default=os.getenv("ALLOWED_PLUGINS", "ua_blocker"),
    ),
)
EDITABLE_SETTING_MAP = {setting.key: setting for setting in EDITABLE_SETTINGS}

SECRET_REFERENCE_SETTINGS: tuple[SecretReferenceSetting, ...] = (
    SecretReferenceSetting(
        label="Redis Password",
        file_env="REDIS_PASSWORD_FILE",
        vault_env="REDIS_PASSWORD_FILE_VAULT_PATH",
    ),
    SecretReferenceSetting(
        label="Cloud CDN API Token",
        file_env="CLOUD_CDN_API_TOKEN_FILE",
        vault_env="CLOUD_CDN_API_TOKEN_FILE_VAULT_PATH",
    ),
    SecretReferenceSetting(
        label="JWT Secret",
        file_env="AUTH_JWT_SECRET_FILE",
        vault_env="AUTH_JWT_SECRET_FILE_VAULT_PATH",
    ),
    SecretReferenceSetting(
        label="JWT Public Key",
        file_env="AUTH_JWT_PUBLIC_KEY_FILE",
        vault_env="AUTH_JWT_PUBLIC_KEY_FILE_VAULT_PATH",
    ),
    SecretReferenceSetting(
        label="SMTP Password",
        file_env="ALERT_SMTP_PASSWORD_FILE",
        vault_env="ALERT_SMTP_PASSWORD_FILE_VAULT_PATH",
    ),
    SecretReferenceSetting(
        label="Admin UI 2FA Seed",
        file_env="ADMIN_UI_2FA_SECRET_FILE",
        vault_env="ADMIN_UI_2FA_SECRET_FILE_VAULT_PATH",
    ),
)

WEBAUTHN_TOKEN_TTL = 300


def _get_runtime_setting(name: str) -> str:
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    with trace_span("admin_ui.runtime_setting", attributes={"setting": name}):
        value = redis_conn.hget(RUNTIME_SETTINGS_KEY, name)
        if value is None:
            default = EDITABLE_SETTING_MAP[name].default
            redis_conn.hset(RUNTIME_SETTINGS_KEY, name, default)
            return default
        return value


def _set_runtime_setting(name: str, value: str) -> None:
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    with trace_span("admin_ui.set_runtime_setting", attributes={"setting": name}):
        redis_conn.hset(RUNTIME_SETTINGS_KEY, name, value)


def _parse_positive_int_setting(name: str, value: str) -> str:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return str(parsed)


def _normalize_bool_setting(name: str, value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return normalized


def _validate_url_setting(name: str, value: str) -> str:
    candidate = (value or "").strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{name} must be an absolute http(s) URL")
    return candidate


def _validate_select_setting(name: str, value: str, choices: set[str]) -> str:
    normalized = (value or "").strip()
    if normalized not in choices:
        raise ValueError(f"{name} must be one of: {', '.join(sorted(choices))}")
    return normalized


def _validate_plugin_setting(name: str, values: list[str]) -> str:
    available = set(_discover_plugins())
    if not values:
        return ""
    if not available:
        return ",".join(dict.fromkeys(values))
    unknown = sorted(set(values) - available)
    if unknown:
        raise ValueError(f"{name} contains unknown plugins: {', '.join(unknown)}")
    return ",".join(dict.fromkeys(values))


def _serialize_secret_reference(
    setting: SecretReferenceSetting,
) -> dict[str, str | bool]:
    file_reference = os.getenv(setting.file_env, "").strip()
    vault_reference = os.getenv(setting.vault_env, "").strip()
    if vault_reference:
        return {
            "label": setting.label,
            "source": "Vault path",
            "reference": vault_reference,
            "configured": True,
        }
    if file_reference:
        return {
            "label": setting.label,
            "source": "File path",
            "reference": file_reference,
            "configured": True,
        }
    return {
        "label": setting.label,
        "source": "Unconfigured",
        "reference": "Not configured",
        "configured": False,
    }


def _serialize_editable_setting(
    setting: EditableSetting, errors: dict[str, str], plugin_options: list[str]
) -> dict[str, object]:
    value = _get_runtime_setting(setting.key)
    selected_values = [entry for entry in value.split(",") if entry]
    return {
        "key": setting.key,
        "label": setting.label,
        "description": setting.description,
        "input_type": setting.input_type,
        "value": value,
        "choices": setting.choices,
        "options": (
            plugin_options if setting.key == "ALLOWED_PLUGINS" else setting.choices
        ),
        "selected_values": selected_values,
        "error": errors.get(setting.key, ""),
    }


def _get_settings_page_context(
    errors: dict[str, str] | None = None, updated: bool = False
) -> dict[str, object]:
    errors = errors or {}
    plugin_options = _discover_plugins()
    current_settings = {
        "Model URI": os.getenv("MODEL_URI", "Not Set"),
        "GDPR_ENABLED": os.getenv("GDPR_ENABLED", "true"),
        "GDPR_DPO_EMAIL": os.getenv("GDPR_DPO_EMAIL", "dpo@example.com"),
        "GDPR_DATA_RETENTION_DAYS": os.getenv("GDPR_DATA_RETENTION_DAYS", "365"),
    }
    context: dict[str, object] = {
        "settings": current_settings,
        "editable_settings": [
            _serialize_editable_setting(setting, errors, plugin_options)
            for setting in EDITABLE_SETTINGS
        ],
        "secret_references": [
            _serialize_secret_reference(setting)
            for setting in SECRET_REFERENCE_SETTINGS
        ],
        "updated": updated,
        "errors": errors,
    }
    return context


def _discover_plugins() -> list[str]:
    """Return a list of available plugin module names."""
    plugin_dir = os.getenv("PLUGIN_DIR", "/app/plugins")
    names: list[str] = []
    with trace_span("admin_ui.discover_plugins", attributes={"plugin_dir": plugin_dir}):
        if os.path.isdir(plugin_dir):
            for fn in os.listdir(plugin_dir):
                if fn.endswith(".py") and not fn.startswith("_"):
                    names.append(fn[:-3])
    return sorted(names)


DEFAULT_ALLOWED_ORIGINS = [f"{os.getenv('ADMIN_UI_CORS_SCHEME', 'http')}://localhost"]


def _get_allowed_origins() -> list[str]:
    """Return a validated list of CORS origins for the Admin UI."""
    raw = os.getenv("ADMIN_UI_CORS_ORIGINS", ",".join(DEFAULT_ALLOWED_ORIGINS))
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if not origins:
        origins = DEFAULT_ALLOWED_ORIGINS.copy()
    if "*" in origins:
        raise ValueError(
            "ADMIN_UI_CORS_ORIGINS cannot include '*' when allow_credentials is True"
        )
    return origins


DEFAULT_ALLOWED_METHODS = ["GET", "POST", "OPTIONS"]
DEFAULT_ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Requested-With",
    "X-CSRF-Token",
]


def _parse_allowed_list(
    env_var: str,
    default: list[str],
    *,
    normalizer=lambda value: value,
) -> list[str]:
    """Parse comma-separated values from env vars with validation."""
    raw = os.getenv(env_var, "")
    values: list[str] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        normalised = normalizer(chunk)
        values.append(normalised)
    if not values:
        return default
    if any(value == "*" for value in values):
        raise ValueError(f"{env_var} cannot include '*' when allow_credentials is True")
    unique_values: list[str] = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    return unique_values


def _get_allowed_methods() -> list[str]:
    """Return validated HTTP methods for CORS preflight handling."""
    return _parse_allowed_list(
        "ADMIN_UI_CORS_METHODS",
        DEFAULT_ALLOWED_METHODS,
        normalizer=lambda value: value.upper(),
    )


def _get_allowed_headers() -> list[str]:
    """Return validated headers permitted in CORS requests."""
    return _parse_allowed_list("ADMIN_UI_CORS_HEADERS", DEFAULT_ALLOWED_HEADERS)


def _ensure_csrf_token(csrf_token: str | None) -> str:
    if not csrf_token:
        return secrets.token_urlsafe(16)
    return csrf_token


def _validate_csrf(csrf_cookie: str | None, submitted: str | None) -> None:
    if not csrf_cookie or not submitted or csrf_cookie != submitted:
        raise HTTPException(status_code=400, detail="Invalid CSRF token")


app = create_app(
    observability_settings=ObservabilitySettings(
        metrics_path="/observability/metrics",
        health_path="/observability/health",
    )
)
_ALLOWED_ORIGINS = _get_allowed_origins()
_ALLOWED_METHODS = _get_allowed_methods()
_ALLOWED_HEADERS = _get_allowed_headers()
logger.debug(
    "Configured Admin UI CORS: origins=%s methods=%s headers=%s",
    _ALLOWED_ORIGINS,
    _ALLOWED_METHODS,
    _ALLOWED_HEADERS,
)


@register_health_check(app, "redis", critical=True)
async def _redis_health() -> HealthCheckResult:
    redis_conn = get_redis_connection()
    if not redis_conn:
        return HealthCheckResult.degraded({"reason": "redis connection unavailable"})
    try:
        cache_keys = None
        if hasattr(redis_conn, "ping"):
            redis_conn.ping()
        if hasattr(redis_conn, "dbsize"):
            cache_keys = redis_conn.dbsize()
    except RedisError as exc:  # pragma: no cover - network interaction
        return HealthCheckResult.unhealthy({"error": str(exc)})
    return HealthCheckResult.healthy({"cache_keys": cache_keys})


app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=_ALLOWED_METHODS,
    allow_headers=_ALLOWED_HEADERS,
)

DEFAULT_CSP = "default-src 'self'"


@app.middleware("http")
async def csp_header(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault(
        "Content-Security-Policy", os.getenv("ADMIN_UI_CSP", DEFAULT_CSP)
    )
    session_id = getattr(request.state, "admin_ui_session_cookie", None)
    if session_id:
        session_ttl = getattr(
            request.state, "admin_ui_session_ttl", auth_routes.SESSION_TTL
        )
        response.set_cookie(
            auth_routes.SESSION_COOKIE_NAME,
            session_id,
            max_age=session_ttl,
            httponly=True,
            secure=True,
            samesite=auth_routes.SESSION_COOKIE_SAMESITE,
            path=auth_routes.SESSION_COOKIE_PATH,
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
    user: str = Depends(require_admin),
):
    """Renders the system settings page with a CSRF token."""
    csrf_token = _ensure_csrf_token(csrf_token)

    # Get GDPR compliance report
    gdpr_report = {}
    try:
        from src.shared.gdpr import get_gdpr_manager

        gdpr = get_gdpr_manager()
        gdpr_report = gdpr.generate_compliance_report()
    except Exception as e:
        logger.warning(f"Failed to generate GDPR report: {e}")

    security_kpis = {}
    try:
        security_kpis = metrics.get_security_kpis()
    except Exception as e:
        logger.warning("Failed to load security KPIs: %s", e)

    page_context = _get_settings_page_context()
    response = templates.TemplateResponse(
        request,
        "settings.html",
        {
            "csrf_token": csrf_token,
            "gdpr_report": gdpr_report,
            "security_kpis": security_kpis,
            "user": user,
            **page_context,
        },
    )
    response.set_cookie(
        "csrf_token",
        csrf_token,
        httponly=True,
        secure=True,
        samesite="Strict",
        path="/",
        max_age=CSRF_COOKIE_TTL,
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
    _validate_csrf(csrf_token, form.get("csrf_token"))
    pending_values: dict[str, str] = {}
    errors: dict[str, str] = {}

    for setting in EDITABLE_SETTINGS:
        if setting.key == "ALLOWED_PLUGINS":
            if "ALLOWED_PLUGINS" in form:
                raw_plugins = [
                    value.strip() for value in form.getlist("ALLOWED_PLUGINS")
                ]
            else:
                raw_plugins = [
                    value.strip()
                    for value in _get_runtime_setting("ALLOWED_PLUGINS").split(",")
                    if value.strip()
                ]
            try:
                pending_values[setting.key] = _validate_plugin_setting(
                    setting.label, raw_plugins
                )
            except ValueError as exc:
                errors[setting.key] = str(exc)
            continue

        raw_value = form.get(setting.key)
        if raw_value is None:
            raw_value = _get_runtime_setting(setting.key)
        raw_value = raw_value.strip()
        try:
            if setting.key == "LOG_LEVEL":
                pending_values[setting.key] = _validate_select_setting(
                    setting.label, raw_value.upper(), ALLOWED_LOG_LEVELS
                )
            elif setting.key == "ESCALATION_ENDPOINT":
                pending_values[setting.key] = _validate_url_setting(
                    setting.label, raw_value
                )
            elif setting.key == "WEBAUTHN_AUTHENTICATOR_ATTACHMENT":
                pending_values[setting.key] = _validate_select_setting(
                    setting.label, raw_value, WEBAUTHN_ATTACHMENT_OPTIONS
                )
            elif setting.key in {
                "RATE_LIMIT_REQUESTS",
                "RATE_LIMIT_WINDOW",
                "MAX_BODY_SIZE",
            }:
                pending_values[setting.key] = _parse_positive_int_setting(
                    setting.label, raw_value
                )
            elif setting.key == "ENABLE_HTTPS":
                pending_values[setting.key] = _normalize_bool_setting(
                    setting.label, raw_value
                )
            else:
                pending_values[setting.key] = raw_value
        except ValueError as exc:
            errors[setting.key] = str(exc)

    if errors:
        page_context = _get_settings_page_context(errors=errors, updated=False)
        page_context["editable_settings"] = [
            {
                **entry,
                "value": pending_values.get(entry["key"], entry["value"]),
                "selected_values": (
                    pending_values.get(entry["key"], entry["value"]).split(",")
                    if entry["key"] == "ALLOWED_PLUGINS"
                    else entry["selected_values"]
                ),
            }
            for entry in page_context["editable_settings"]  # type: ignore[index]
        ]
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "csrf_token": csrf_token,
                "gdpr_report": {},
                "security_kpis": {},
                "user": user,
                **page_context,
            },
            status_code=400,
        )

    for key, value in pending_values.items():
        _set_runtime_setting(key, value)
        os.environ[key] = value

    log_event(
        user,
        "update_settings",
        {"updated_settings": pending_values},
    )

    page_context = _get_settings_page_context(updated=True)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "csrf_token": csrf_token,
            "gdpr_report": {},
            "security_kpis": {},
            "user": user,
            **page_context,
        },
    )


@app.get("/logs", response_class=HTMLResponse)
async def view_logs(request: Request, user: str = Depends(require_auth)):
    """Display recent block events."""
    events = blocklist._load_recent_block_events_func(50)
    return templates.TemplateResponse(request, "logs.html", {"events": events})


@app.get("/plugins", response_class=HTMLResponse)
async def plugins_page(request: Request, user: str = Depends(require_auth)):
    """Show available plugins and which are enabled."""
    csrf_token = _ensure_csrf_token(request.cookies.get("csrf_token"))
    available = _discover_plugins()
    allowed_plugins = _get_runtime_setting("ALLOWED_PLUGINS")
    enabled = allowed_plugins.split(",") if allowed_plugins else []
    response = templates.TemplateResponse(
        request,
        "plugins.html",
        {"available": available, "enabled": enabled, "csrf_token": csrf_token},
    )
    response.set_cookie(
        "csrf_token",
        csrf_token,
        httponly=True,
        secure=True,
        samesite="Strict",
        path="/",
        max_age=CSRF_COOKIE_TTL,
    )
    return response


@app.post("/plugins")
async def update_plugins(request: Request, user: str = Depends(require_admin)):
    """Update enabled plugins and notify the escalation engine."""
    form = await request.form()
    _validate_csrf(request.cookies.get("csrf_token"), form.get("csrf_token"))
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


@app.post("/gdpr/deletion-request")
async def gdpr_deletion_request(request: Request, user: str = Depends(require_admin)):
    """Handle GDPR data deletion request."""
    from src.shared.gdpr import get_gdpr_manager

    _validate_csrf(
        request.cookies.get("csrf_token"), request.headers.get("X-CSRF-Token")
    )

    # Allowed characters for user_id validation
    ALLOWED_USER_ID_CHARS = "-_"
    MAX_USER_ID_LENGTH = 255

    form = await request.form()
    user_id = form.get("user_id", "").strip()
    email = form.get("email", "").strip()

    # Validate user_id
    if not user_id:
        return JSONResponse(status_code=400, content={"error": "user_id is required"})

    # Basic validation: alphanumeric, dashes, underscores only
    if not all(c.isalnum() or c in ALLOWED_USER_ID_CHARS for c in user_id):
        return JSONResponse(
            status_code=400, content={"error": "user_id contains invalid characters"}
        )

    # Limit length to prevent abuse
    if len(user_id) > MAX_USER_ID_LENGTH:
        return JSONResponse(status_code=400, content={"error": "user_id is too long"})

    gdpr = get_gdpr_manager()
    deletion_request = gdpr.request_data_deletion(user_id=user_id, email=email or None)

    log_event(
        user,
        "gdpr_deletion_request",
        {
            "user_id": user_id,
            "email": email or "none",
            "request_id": deletion_request.request_id,
        },
    )

    return JSONResponse(
        content={
            "request_id": deletion_request.request_id,
            "status": "pending",
            "message": "Data deletion request submitted successfully",
        }
    )


@app.get("/gdpr/compliance-report")
async def gdpr_compliance_report(request: Request, user: str = Depends(require_auth)):
    """Generate and return GDPR compliance report."""
    from src.shared.gdpr import get_gdpr_manager

    gdpr = get_gdpr_manager()
    report = gdpr.generate_compliance_report()

    return JSONResponse(content=report)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.getenv("ADMIN_UI_PORT", 5002))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    uvicorn.run("src.admin_ui.admin_ui:app", host=host, port=port, log_level=log_level)
