# src/admin_ui/admin_ui.py
"""FastAPI admin interface for monitoring and management.

This module assembles the FastAPI application and wires in
submodules that handle authentication, metrics, blocklist
management and WebAuthn support.
"""

import datetime
import hashlib
import hmac
import json
import logging
import os
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import Cookie, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from redis.exceptions import RedisError

from src.shared.audit import log_event
from src.shared.config import CONFIG, get_secret, tenant_key
from src.shared.middleware import create_app
from src.shared.observability import (
    HealthCheckResult,
    ObservabilitySettings,
    register_health_check,
    trace_span,
)
from src.shared.redis_client import get_redis_connection

from . import auth as auth_routes
from . import block_log, blocklist, metrics, mfa, passkeys, webauthn
from .auth import require_admin, require_auth

logger = logging.getLogger(__name__)

CSRF_COOKIE_TTL = int(os.getenv("ADMIN_UI_CSRF_COOKIE_TTL", "3600"))

BASE_DIR = os.path.dirname(__file__)

# Editable runtime settings managed via the Admin UI
RUNTIME_SETTINGS_KEY = tenant_key("admin_ui:settings")
# Who last changed each setting and when, kept beside the settings so the lookup is exact and never windowed.
RUNTIME_SETTINGS_META_KEY = tenant_key("admin_ui:settings_changes")
ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
WEBAUTHN_ATTACHMENT_OPTIONS = {"none", "platform", "cross-platform"}
CAPTCHA_PROVIDER_OPTIONS = {"builtin", "recaptcha", "turnstile"}


@dataclass(frozen=True)
class EditableSetting:
    key: str
    label: str
    description: str
    input_type: str
    default: str
    choices: tuple[str, ...] = ()
    builtin: str | None = None  # the shipped default, independent of the environment
    valid: str = ""  # what the server-side validation accepts, in plain words
    risky: bool = False  # changing it can lock an admin out or weaken security


@dataclass(frozen=True)
class SecretReferenceSetting:
    label: str
    file_env: str
    vault_env: str


_BUILTIN_DEFAULTS = {
    "LOG_LEVEL": "INFO",
    "WEBAUTHN_AUTHENTICATOR_ATTACHMENT": "none",
    "RATE_LIMIT_REQUESTS": "100",
    "RATE_LIMIT_WINDOW": "60",
    "MAX_BODY_SIZE": str(1 * 1024 * 1024),
    "ENABLE_HTTPS": "false",
    "ALLOWED_PLUGINS": "ua_blocker",
    "CAPTCHA_PROVIDER": "builtin",
    "CAPTCHA_MANUAL_REQUESTS_ENABLED": "false",
    "CLOUDFLARE_ENABLED": "false",
    "CLOUDFLARE_UNDER_ATTACK_THRESHOLD": "100",
}

EDITABLE_SETTINGS: tuple[EditableSetting, ...] = (
    EditableSetting(
        key="LOG_LEVEL",
        label="Log Level",
        description="Controls admin UI logging verbosity.",
        input_type="select",
        default=os.getenv("LOG_LEVEL", _BUILTIN_DEFAULTS["LOG_LEVEL"]),
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        builtin=_BUILTIN_DEFAULTS["LOG_LEVEL"],
        valid="One of DEBUG, INFO, WARNING, ERROR, CRITICAL.",
    ),
    EditableSetting(
        key="ESCALATION_ENDPOINT",
        label="Escalation Engine URL",
        description="Absolute HTTP(S) URL for escalation requests.",
        input_type="text",
        default=CONFIG.ESCALATION_ENDPOINT,
        valid="An absolute http:// or https:// URL.",
        risky=True,
    ),
    EditableSetting(
        key="WEBAUTHN_AUTHENTICATOR_ATTACHMENT",
        label="WebAuthn Authenticator Preference",
        description="Preferred authenticator attachment for admin login.",
        input_type="select",
        default=os.getenv(
            "WEBAUTHN_AUTHENTICATOR_ATTACHMENT",
            _BUILTIN_DEFAULTS["WEBAUTHN_AUTHENTICATOR_ATTACHMENT"],
        ),
        choices=("none", "platform", "cross-platform"),
        builtin=_BUILTIN_DEFAULTS["WEBAUTHN_AUTHENTICATOR_ATTACHMENT"],
        valid="One of none, platform, cross-platform.",
    ),
    EditableSetting(
        key="RATE_LIMIT_REQUESTS",
        label="Rate Limit Requests",
        description="Maximum requests allowed per rate-limit window.",
        input_type="number",
        default=os.getenv("RATE_LIMIT_REQUESTS", _BUILTIN_DEFAULTS["RATE_LIMIT_REQUESTS"]),
        builtin=_BUILTIN_DEFAULTS["RATE_LIMIT_REQUESTS"],
        valid="A whole number of at least 1.",
    ),
    EditableSetting(
        key="RATE_LIMIT_WINDOW",
        label="Rate Limit Window (seconds)",
        description="Rate-limit window size in seconds.",
        input_type="number",
        default=os.getenv("RATE_LIMIT_WINDOW", _BUILTIN_DEFAULTS["RATE_LIMIT_WINDOW"]),
        builtin=_BUILTIN_DEFAULTS["RATE_LIMIT_WINDOW"],
        valid="A whole number of seconds, at least 1.",
    ),
    EditableSetting(
        key="MAX_BODY_SIZE",
        label="Max Body Size (bytes)",
        description="Largest request body accepted by shared middleware.",
        input_type="number",
        default=os.getenv("MAX_BODY_SIZE", _BUILTIN_DEFAULTS["MAX_BODY_SIZE"]),
        builtin=_BUILTIN_DEFAULTS["MAX_BODY_SIZE"],
        valid="A whole number of bytes, at least 1 (1048576 is 1 MiB).",
    ),
    EditableSetting(
        key="ENABLE_HTTPS",
        label="HTTPS Redirect Enforcement",
        description="Redirect plain HTTP requests to HTTPS in shared middleware.",
        input_type="select",
        default=os.getenv("ENABLE_HTTPS", _BUILTIN_DEFAULTS["ENABLE_HTTPS"]),
        choices=("true", "false"),
        builtin=_BUILTIN_DEFAULTS["ENABLE_HTTPS"],
        valid="true or false. Turning it off stops redirecting plain HTTP to HTTPS.",
        risky=True,
    ),
    EditableSetting(
        key="ALLOWED_PLUGINS",
        label="Allowed Plugins",
        description="Comma-separated plugin allowlist pushed to the escalation engine.",
        input_type="multiselect",
        default=os.getenv("ALLOWED_PLUGINS", _BUILTIN_DEFAULTS["ALLOWED_PLUGINS"]),
        builtin=_BUILTIN_DEFAULTS["ALLOWED_PLUGINS"],
        valid="Any of the plugins listed here; none selected disables the allowlist.",
    ),
    EditableSetting(
        key="CAPTCHA_PROVIDER",
        label="CAPTCHA Provider",
        description=(
            "Selects built-in CAPTCHA (no third-party calls) or an external provider "
            "(Google reCAPTCHA or Cloudflare Turnstile; external providers receive visitor IPs and tokens under your privacy notice)."
        ),
        input_type="select",
        default=os.getenv("CAPTCHA_PROVIDER", _BUILTIN_DEFAULTS["CAPTCHA_PROVIDER"]),
        choices=("builtin", "recaptcha", "turnstile"),
        builtin=_BUILTIN_DEFAULTS["CAPTCHA_PROVIDER"],
        valid="One of builtin, recaptcha, turnstile.",
    ),
    EditableSetting(
        key="CAPTCHA_MANUAL_REQUESTS_ENABLED",
        label="Allow Manual CAPTCHA Access Requests",
        description="Off by default. Lets visitors ask an admin for temporary IP access when they cannot solve the built-in CAPTCHA.",
        input_type="select",
        default=os.getenv(
            "CAPTCHA_MANUAL_REQUESTS_ENABLED",
            _BUILTIN_DEFAULTS["CAPTCHA_MANUAL_REQUESTS_ENABLED"],
        ),
        choices=("false", "true"),
        builtin=_BUILTIN_DEFAULTS["CAPTCHA_MANUAL_REQUESTS_ENABLED"],
        valid="true or false.",
    ),
    EditableSetting(
        key="CLOUDFLARE_ENABLED",
        label="Site Uses Cloudflare",
        description="Enables a dashboard prompt suggesting Cloudflare Under Attack mode during high block/queue volume (never calls Cloudflare's API).",
        input_type="select",
        default=os.getenv("CLOUDFLARE_ENABLED", _BUILTIN_DEFAULTS["CLOUDFLARE_ENABLED"]),
        choices=("false", "true"),
        builtin=_BUILTIN_DEFAULTS["CLOUDFLARE_ENABLED"],
        valid="true or false.",
    ),
    EditableSetting(
        key="CLOUDFLARE_UNDER_ATTACK_THRESHOLD",
        label="Cloudflare Under Attack Suggestion Threshold",
        description="Blocked + queued access-request count that triggers the Under Attack mode banner when Site Uses Cloudflare is true.",
        input_type="number",
        default=os.getenv(
            "CLOUDFLARE_UNDER_ATTACK_THRESHOLD",
            _BUILTIN_DEFAULTS["CLOUDFLARE_UNDER_ATTACK_THRESHOLD"],
        ),
        builtin=_BUILTIN_DEFAULTS["CLOUDFLARE_UNDER_ATTACK_THRESHOLD"],
        valid="A whole number of at least 1.",
    ),
)
EDITABLE_SETTING_MAP = {setting.key: setting for setting in EDITABLE_SETTINGS}
# What the environment supplied at start-up. Saving a setting later writes os.environ, so this is captured once.
STARTUP_ENV = {setting.key: os.environ.get(setting.key) for setting in EDITABLE_SETTINGS}

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


def _risky_changes(
    changed: list[str], pending: dict[str, str], current: dict[str, str]
) -> list[dict[str, str]]:
    """Changes that need an explicit confirmation: HTTPS redirect turned off, or a new escalation URL."""
    risky: list[dict[str, str]] = []
    for key in changed:
        setting = EDITABLE_SETTING_MAP[key]
        if not setting.risky:
            continue
        if key == "ENABLE_HTTPS" and pending[key] != "false":
            continue  # turning the redirect on is not a weakening
        risky.append(
            {
                "key": key,
                "label": setting.label,
                "old": current[key],
                "new": pending[key],
                "why": (
                    "Plain HTTP requests will no longer be redirected to HTTPS."
                    if key == "ENABLE_HTTPS"
                    else "Escalation requests will be sent to a different URL; a wrong or hostile URL "
                    "receives request details and can stop escalations."
                ),
            }
        )
    return risky


def _risk_confirmation_token(risky: list[dict[str, str]]) -> str:
    """Binds a confirmation to the exact risky values shown, so editing them afterwards needs a new confirmation."""
    material = "\n".join(f"{item['key']}={item['new']}" for item in risky)
    return hashlib.sha256(material.encode()).hexdigest() if risky else ""


def _record_setting_change(name: str, actor: str) -> None:
    """Remember who changed a setting and when. Never lets a bookkeeping failure undo a saved change."""
    try:
        redis_conn = get_redis_connection()
        if redis_conn:
            stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="seconds"
            )
            redis_conn.hset(
                RUNTIME_SETTINGS_META_KEY,
                name,
                json.dumps({"actor": actor, "at": stamp}),
            )
    except Exception as exc:
        logger.warning("Could not record who changed %s: %s", name, exc)


def _decode(value) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _parse_change_entry(value) -> dict[str, str] | None:
    """One stored change record as {actor, at}, or None when it is not a usable record."""
    try:
        entry = json.loads(_decode(value))
    except (ValueError, AttributeError):
        return None
    if not isinstance(entry, dict):
        return None
    return {
        "actor": str(entry.get("actor") or "unknown"),
        "at": str(entry.get("at") or ""),
    }


def _last_changes() -> dict[str, dict[str, str]]:
    """Who last changed each setting and when, from the record kept beside the settings.

    Both the Settings and the Plugins pages write it whenever a value actually changes. It starts empty on an
    existing installation, so a setting shows no change until its first change after the upgrade.
    """
    try:
        redis_conn = get_redis_connection()
        raw = redis_conn.hgetall(RUNTIME_SETTINGS_META_KEY) if redis_conn else {}
    except Exception as exc:  # the page must render even when this lookup fails
        logger.warning("Could not read the settings change record: %s", exc)
        return {}
    parsed = {_decode(key): _parse_change_entry(value) for key, value in (raw or {}).items()}
    return {
        name: entry
        for name, entry in parsed.items()
        if name in EDITABLE_SETTING_MAP and entry is not None
    }


def _serialize_editable_setting(
    setting: EditableSetting,
    errors: dict[str, str],
    plugin_options: list[str],
    last_changes: dict[str, dict[str, str]] | None = None,
) -> dict[str, object]:
    value = _get_runtime_setting(setting.key)
    selected_values = [entry for entry in value.split(",") if entry]
    from_environment = STARTUP_ENV.get(setting.key) is not None
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
        "startup_value": setting.default,
        "startup_source": (
            "environment variable" if from_environment else "built-in default"
        ),
        "builtin": setting.builtin,
        "valid": setting.valid,
        "risky": setting.risky,
        "last_changed": (last_changes or {}).get(setting.key),
    }


def _get_settings_page_context(
    errors: dict[str, str] | None = None, updated: bool = False
) -> dict[str, object]:
    errors = errors or {}
    plugin_options = _discover_plugins()
    last_changes = _last_changes()
    current_settings = {
        "Model URI": os.getenv("MODEL_URI", "Not Set"),
        "GDPR_ENABLED": os.getenv("GDPR_ENABLED", "true"),
        "GDPR_DPO_EMAIL": os.getenv("GDPR_DPO_EMAIL", "dpo@example.com"),
        "GDPR_DATA_RETENTION_DAYS": os.getenv("GDPR_DATA_RETENTION_DAYS", "365"),
    }
    context: dict[str, object] = {
        "settings": current_settings,
        "editable_settings": [
            _serialize_editable_setting(setting, errors, plugin_options, last_changes)
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


def _request_is_https(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or forwarded == "https"


def _set_csrf_cookie(response, request: Request, token: str) -> None:
    """Set the CSRF cookie, marking it Secure only when the request arrived over HTTPS.

    A Secure cookie is never sent back over plain HTTP, which would make every protected call fail on the
    documented HTTP deployment. Plain HTTP is already exposed to Basic-credential sniffing, and SameSite=Strict
    still applies.
    """
    response.set_cookie(
        "csrf_token",
        token,
        httponly=True,
        secure=_request_is_https(request),
        samesite="Strict",
        path="/",
        max_age=CSRF_COOKIE_TTL,
    )


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


from src.captcha.access_requests import AccessRequestStore
from src.shared import blocklist_store

access_request_store = AccessRequestStore()


def _safe_runtime_setting(name: str, default: str) -> str:
    try:
        return _get_runtime_setting(name)
    except Exception:
        return os.getenv(name, default)


def _current_blocked_volume() -> int:
    try:
        return int(blocklist.get_block_stats().get("total_blocked", 0))
    except Exception:
        return 0


def _captcha_dashboard_context() -> dict[str, object]:
    pending = access_request_store.list_requests(include_closed=False)
    digest = access_request_store.digest_summary()
    manual_enabled = _safe_runtime_setting("CAPTCHA_MANUAL_REQUESTS_ENABLED", "false").lower() == "true"
    cf_enabled = _safe_runtime_setting("CLOUDFLARE_ENABLED", "false").lower() == "true"
    try:
        threshold = max(1, int(_safe_runtime_setting("CLOUDFLARE_UNDER_ATTACK_THRESHOLD", "100")))
    except ValueError:
        threshold = 100
    volume = _current_blocked_volume() + int(digest["pending_count"])
    return {
        "manual_requests_enabled": manual_enabled,
        "pending_captcha_requests": pending,
        "captcha_request_digest": digest,
        "cloudflare_under_attack_suggested": cf_enabled and volume >= threshold,
    }


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    csrf_token: str | None = Cookie(None),
    user: str = Depends(require_auth),
):
    """Serves the main dashboard HTML page.

    The CSRF cookie is HttpOnly, so the token is also rendered into the page for the blocklist controls.
    """
    csrf_token = _ensure_csrf_token(csrf_token)
    response = templates.TemplateResponse(
        request,
        "index.html",
        {"user": user, "csrf_token": csrf_token, **_captcha_dashboard_context()},
    )
    _set_csrf_cookie(response, request, csrf_token)
    return response


@app.get("/captcha-requests")
async def list_captcha_requests(user: str = Depends(require_auth)):
    return JSONResponse(content=_captcha_dashboard_context())


@app.post("/captcha-requests/{request_id}/approve")
async def approve_captcha_request(
    request_id: str,
    request: Request,
    csrf_token: str | None = Cookie(None),
    user: str = Depends(require_admin),
):
    form = await request.form()
    _validate_csrf(csrf_token, form.get("csrf_token") or request.headers.get("X-CSRF-Token"))
    record = access_request_store.approve(request_id, actor=user)
    if not record:
        raise HTTPException(status_code=404, detail="Access request not found")
    try:
        blocklist_store.unblock(record["ip"])
    except Exception as exc:  # noqa: BLE001 - best-effort unblock when Redis is unavailable in tests
        logger.warning("Could not unblock approved IP %s: %s", record["ip"], exc)
    log_event(user, "captcha_request_approved", {"request_id": request_id, "ip": record["ip"]})
    return JSONResponse(content={"status": "approved", "request": record})


@app.post("/captcha-requests/{request_id}/deny")
async def deny_captcha_request(
    request_id: str,
    request: Request,
    csrf_token: str | None = Cookie(None),
    user: str = Depends(require_admin),
):
    form = await request.form()
    _validate_csrf(csrf_token, form.get("csrf_token") or request.headers.get("X-CSRF-Token"))
    record = access_request_store.deny(request_id, actor=user)
    if not record:
        raise HTTPException(status_code=404, detail="Access request not found")
    log_event(user, "captcha_request_denied", {"request_id": request_id, "ip": record["ip"]})
    return JSONResponse(content={"status": "denied", "request": record})


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
    _set_csrf_cookie(response, request, csrf_token)
    return response


def _validate_single_setting(setting: EditableSetting, raw_value: str) -> str:
    if setting.key == "LOG_LEVEL":
        return _validate_select_setting(setting.label, raw_value.upper(), ALLOWED_LOG_LEVELS)
    if setting.key == "ESCALATION_ENDPOINT":
        return _validate_url_setting(setting.label, raw_value)
    if setting.key == "WEBAUTHN_AUTHENTICATOR_ATTACHMENT":
        return _validate_select_setting(setting.label, raw_value, WEBAUTHN_ATTACHMENT_OPTIONS)
    if setting.key == "CAPTCHA_PROVIDER":
        return _validate_select_setting(setting.label, raw_value.lower(), CAPTCHA_PROVIDER_OPTIONS)
    if setting.key in {"RATE_LIMIT_REQUESTS", "RATE_LIMIT_WINDOW", "MAX_BODY_SIZE", "CLOUDFLARE_UNDER_ATTACK_THRESHOLD"}:
        return _parse_positive_int_setting(setting.label, raw_value)
    if setting.key in {"ENABLE_HTTPS", "CAPTCHA_MANUAL_REQUESTS_ENABLED", "CLOUDFLARE_ENABLED"}:
        return _normalize_bool_setting(setting.label, raw_value)
    return raw_value


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
            pending_values[setting.key] = _validate_single_setting(setting, raw_value)
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

    current_values = {key: _get_runtime_setting(key) for key in pending_values}
    changed = sorted(
        key for key, value in pending_values.items() if value != current_values[key]
    )
    risky = _risky_changes(changed, pending_values, current_values)
    token = _risk_confirmation_token(risky)
    if risky and not hmac.compare_digest(str(form.get("confirm_risky") or ""), token):
        page_context = _get_settings_page_context(updated=False)
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
        page_context["risky_confirmation"] = {"changes": risky, "token": token}
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

    for key, value in pending_values.items():
        _set_runtime_setting(key, value)
        os.environ[key] = value
    for key in changed:
        _record_setting_change(key, user)

    log_event(
        user,
        "update_settings",
        {"updated_settings": pending_values, "changed": changed},
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


_RANGE_PATTERN = "^(" + "|".join(block_log.RANGES) + ")$"


@app.get("/logs", response_class=HTMLResponse)
async def view_logs(
    request: Request,
    q: str = Query("", max_length=block_log.MAX_QUERY_LENGTH),
    range_key: str = Query(
        block_log.DEFAULT_RANGE, alias="range", pattern=_RANGE_PATTERN
    ),
    page: int = Query(1, ge=1, le=block_log.MAX_PAGE),
    page_size: int = Query(
        block_log.DEFAULT_PAGE_SIZE, ge=1, le=block_log.MAX_PAGE_SIZE
    ),
    user: str = Depends(require_auth),
):
    """Display block events with search, a time range and paging."""
    result = block_log.query_events(
        blocklist.BLOCK_LOG_FILE, q, range_key, page, page_size
    )
    return templates.TemplateResponse(
        request,
        "logs.html",
        {
            "events": result.events,
            "result": result,
            "q": q,
            "range": range_key,
            "ranges": list(block_log.RANGES),
            "export_limit": block_log.MAX_EXPORT_ROWS,
            "scan_limit": block_log.MAX_SCAN_LINES,
        },
    )


@app.get("/logs/export.csv")
async def export_logs(
    q: str = Query("", max_length=block_log.MAX_QUERY_LENGTH),
    range_key: str = Query(
        block_log.DEFAULT_RANGE, alias="range", pattern=_RANGE_PATTERN
    ),
    user: str = Depends(require_auth),
):
    """Download the current filter of the block log as CSV."""
    body = block_log.export_csv(blocklist.BLOCK_LOG_FILE, q, range_key)
    log_event(user, "export_block_log", {"range": range_key, "query": q})
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="block-log-{range_key}.csv"',
            "Cache-Control": "no-store",
        },
    )


def _security_page_context(request: Request, user: str) -> dict:
    """Facts for the Security page: identity, sign-in method and which second factors are enrolled."""
    provider = getattr(request.state, "admin_ui_auth_provider", "basic")
    has_session = request.cookies.get(auth_routes.SESSION_COOKIE_NAME) is not None
    if provider == "oidc":
        method = "Single sign-on (OpenID Connect)"
    elif provider == "saml":
        method = "Single sign-on (SAML)"
    elif has_session:
        method = "Username and password (browser session)"
    else:
        method = "Username and password (HTTP Basic)"
    try:
        passkey_enrolled = passkeys._load_credential(user) is not None
    except Exception:  # an unreadable credential store must not break the page
        logger.warning("Could not read the passkey enrolment for the Security page")
        passkey_enrolled = False
    backup = mfa.get_backup_codes_status(user)
    backup["created_text"] = (
        datetime.datetime.fromtimestamp(
            backup["created_at"], datetime.timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")
        if backup["created_at"]
        else None
    )
    return {
        "user": user,
        "method": method,
        # Signing out of the Admin UI only ends the local session; a proxy or provider session stays signed in.
        "sso": provider in {"oidc", "saml"},
        "passkey_enrolled": passkey_enrolled,
        "totp_enabled": bool(
            os.getenv("ADMIN_UI_2FA_SECRET") or get_secret("ADMIN_UI_2FA_SECRET_FILE")
        ),
        "backup": backup,
    }


@app.get("/security", response_class=HTMLResponse)
async def security_page(
    request: Request,
    csrf_token: str | None = Cookie(None),
    user: str = Depends(require_admin),
):
    """Show the signed-in identity and which second factors are enrolled (#1952).

    Backup codes themselves are never rendered here; they are shown once, in the response to the regenerate call.
    """
    csrf_token = _ensure_csrf_token(csrf_token)
    response = templates.TemplateResponse(
        request,
        "security.html",
        {**_security_page_context(request, user), "csrf_token": csrf_token},
    )
    _set_csrf_cookie(response, request, csrf_token)
    response.headers["Cache-Control"] = "no-store"
    return response


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
    _set_csrf_cookie(response, request, csrf_token)
    return response


@app.post("/plugins")
async def update_plugins(request: Request, user: str = Depends(require_admin)):
    """Update enabled plugins and notify the escalation engine."""
    form = await request.form()
    _validate_csrf(request.cookies.get("csrf_token"), form.get("csrf_token"))
    selected = form.getlist("plugins")
    allowed = ",".join(selected)
    previous = _get_runtime_setting("ALLOWED_PLUGINS")
    _set_runtime_setting("ALLOWED_PLUGINS", allowed)
    os.environ["ALLOWED_PLUGINS"] = allowed
    if allowed != previous:
        _record_setting_change("ALLOWED_PLUGINS", user)
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
