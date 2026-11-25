import hmac
import os
import secrets

import bcrypt
import pyotp
from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from redis.exceptions import RedisError

from src.shared.audit import log_event
from src.shared.config import get_secret
from src.shared.metrics import LOGIN_ATTEMPTS, SECURITY_EVENTS
from src.shared.redis_client import get_redis_connection
from src.shared.request_identity import resolve_request_identity

from . import mfa, passkeys, sso

security = HTTPBasic(auto_error=False)
router = APIRouter()

ADMIN_UI_ROLE = os.getenv("ADMIN_UI_ROLE", "admin")
LOCKOUT_THRESHOLD = int(os.getenv("ADMIN_UI_LOCKOUT_THRESHOLD", "5"))
LOCKOUT_DURATION = int(os.getenv("ADMIN_UI_LOCKOUT_DURATION", "900"))
SESSION_TTL = int(os.getenv("ADMIN_UI_SESSION_TTL", "3600"))
SESSION_MAX_CONCURRENT = int(os.getenv("ADMIN_UI_SESSION_MAX_CONCURRENT", "3"))
SESSION_COOKIE_NAME = os.getenv("ADMIN_UI_SESSION_COOKIE", "admin_ui_session")
SESSION_COOKIE_PATH = "/"
SESSION_COOKIE_SAMESITE = "Strict"


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() == "true"


def _admin_ui_mfa_required() -> bool:
    return _env_flag("ADMIN_UI_REQUIRE_MFA", True)


def _admin_ui_sso_mfa_required() -> bool:
    value = os.getenv("ADMIN_UI_SSO_MFA_REQUIRED")
    if value is not None:
        return value.lower() == "true"
    return _admin_ui_mfa_required()


def _lockout_key(username: str) -> str:
    return f"admin_ui:lockout:{username}"


def _failure_key(username: str) -> str:
    return f"admin_ui:auth_fail:{username}"


def _session_key(session_id: str) -> str:
    return f"admin_ui:session:{session_id}"


def _session_index_key(username: str) -> str:
    return f"admin_ui:sessions:{username}"


def _decode_redis(value) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return value


def _get_session_user(redis_conn, session_id: str | None) -> str | None:
    if not redis_conn or not session_id or SESSION_TTL <= 0:
        return None
    try:
        user = redis_conn.get(_session_key(session_id))
        if not user:
            return None
        redis_conn.expire(_session_key(session_id), SESSION_TTL)
        return _decode_redis(user)
    except RedisError:
        return None


def _issue_session(redis_conn, username: str) -> str | None:
    if not redis_conn or SESSION_TTL <= 0:
        return None
    session_id = secrets.token_urlsafe(32)
    try:
        redis_conn.set(_session_key(session_id), username, ex=SESSION_TTL)
        if SESSION_MAX_CONCURRENT > 0:
            index_key = _session_index_key(username)
            redis_conn.lpush(index_key, session_id)
            redis_conn.expire(index_key, SESSION_TTL)
            sessions = [
                _decode_redis(entry) for entry in redis_conn.lrange(index_key, 0, -1)
            ]
            if len(sessions) > SESSION_MAX_CONCURRENT:
                drop = sessions[SESSION_MAX_CONCURRENT:]
                redis_conn.ltrim(index_key, 0, SESSION_MAX_CONCURRENT - 1)
                for old_session_id in drop:
                    redis_conn.delete(_session_key(old_session_id))
    except RedisError:
        return None
    return session_id


def _clear_session(redis_conn, session_id: str | None) -> None:
    if not redis_conn or not session_id:
        return
    try:
        user = redis_conn.get(_session_key(session_id))
        redis_conn.delete(_session_key(session_id))
        if user:
            index_key = _session_index_key(_decode_redis(user))
            redis_conn.lrem(index_key, 0, session_id)
    except RedisError:
        return


def _rate_key(client_ip: str) -> str:
    return f"admin_ui:auth:{client_ip}"


def _release_rate_slot(redis_conn, client_ip: str) -> None:
    """Hand back the slot reserved for a sign-in whose password was correct."""
    try:
        redis_conn.decr(_rate_key(client_ip))
    except RedisError:
        pass


def _record_failed_attempt(redis_conn, username: str) -> None:
    if not redis_conn:
        return
    try:
        count = redis_conn.incr(_failure_key(username))
        if count == 1:
            redis_conn.expire(_failure_key(username), LOCKOUT_DURATION)
        if count >= LOCKOUT_THRESHOLD:
            redis_conn.set(_lockout_key(username), "1", ex=LOCKOUT_DURATION)
    except RedisError:
        pass


def _require_mfa(
    request: Request | None,
    response: Response | None,
    redis_conn,
    username: str,
    session_user: str | None,
    x_2fa_code: str | None,
    x_2fa_token: str | None,
    x_2fa_backup_code: str | None,
    *,
    force: bool,
) -> str:
    """Validate 2FA for the given username."""
    from . import webauthn

    token_user = passkeys._consume_passkey_token(
        x_2fa_token
    ) or webauthn._consume_webauthn_token(x_2fa_token)
    if token_user and token_user != username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA token",
            headers={"WWW-Authenticate": "Basic"},
        )

    totp_secret = (
        mfa.get_totp_secret(username)
        or os.getenv("ADMIN_UI_2FA_SECRET")
        or get_secret("ADMIN_UI_2FA_SECRET_FILE")
    )
    session_valid = session_user == username
    if totp_secret:
        if token_user or session_valid:
            if redis_conn:
                redis_conn.delete(_failure_key(username))
            if not session_valid:
                _set_session_cookie(response, request, redis_conn, username)
            return username
        if x_2fa_code:
            totp = pyotp.TOTP(totp_secret)

            if totp.verify(x_2fa_code, valid_window=1):
                if redis_conn:
                    redis_conn.delete(_failure_key(username))
                _set_session_cookie(response, request, redis_conn, username)
                return username
            detail = "Invalid 2FA code"
        elif x_2fa_backup_code:
            if mfa.verify_backup_code(username, x_2fa_backup_code):
                if redis_conn:
                    redis_conn.delete(_failure_key(username))
                _set_session_cookie(response, request, redis_conn, username)
                return username
            detail = "Invalid backup code"
        else:
            detail = "2FA token, code, or backup code required"
        _record_failed_attempt(redis_conn, username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Basic"},
        )

    if token_user or session_valid:
        if redis_conn:
            redis_conn.delete(_failure_key(username))
        if not session_valid:
            _set_session_cookie(response, request, redis_conn, username)
        return username
    if (
        force
        and (passkeys._has_passkey_tokens() or webauthn._has_webauthn_tokens())
        and not token_user
    ):
        _record_failed_attempt(redis_conn, username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="2FA token required",
            headers={"WWW-Authenticate": "Basic"},
        )
    if force:
        _record_failed_attempt(redis_conn, username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA required",
            headers={"WWW-Authenticate": "Basic"},
        )
    if redis_conn:
        redis_conn.delete(_failure_key(username))
    _set_session_cookie(response, request, redis_conn, username)
    return username


def _require_auth_core(
    request: Request | None,
    response: Response | None,
    credentials: HTTPBasicCredentials | None,
    x_2fa_code: str | None,
    x_2fa_token: str | None,
    x_2fa_backup_code: str | None,
    client_ip: str | None,
) -> str:
    """Validate HTTP Basic credentials, SSO, and optional 2FA."""

    rate_limit = int(os.getenv("ADMIN_UI_RATE_LIMIT", "5"))
    rate_window = int(os.getenv("ADMIN_UI_RATE_LIMIT_WINDOW", "60"))
    if client_ip is None:
        if request is None or not request.client or not request.client.host:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot determine client IP address for rate limiting",
            )
        client_ip = resolve_request_identity(request).activity_key
    redis_conn = get_redis_connection()
    session_id = None
    session_user = None
    if request is not None:
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        session_user = _get_session_user(redis_conn, session_id)
    sso_user = None
    if request is not None:
        sso_user = sso.get_sso_user(request)
    if sso_user:
        username = sso_user["username"]
        request.state.admin_ui_auth_provider = sso_user.get("provider", "sso")
        request.state.admin_ui_roles = set(
            sso_user.get("roles", sso_user.get("groups", []))
        )
        sso_mfa_required = _admin_ui_sso_mfa_required()
        if not sso_mfa_required:
            if redis_conn:
                redis_conn.delete(_failure_key(username))
            if session_user != username:
                _set_session_cookie(response, request, redis_conn, username)
            return username
        return _require_mfa(
            request,
            response,
            redis_conn,
            username,
            session_user,
            x_2fa_code,
            x_2fa_token,
            x_2fa_backup_code,
            force=sso_mfa_required,
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing basic auth credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    rate_slot = False
    if redis_conn:
        try:
            if redis_conn.get(_lockout_key(credentials.username)):
                LOGIN_ATTEMPTS.labels(result="locked_out").inc()
                SECURITY_EVENTS.labels(event_type="admin_ui_lockout").inc()
                log_event(
                    credentials.username,
                    "admin_ui_auth_locked_out",
                    {"ip": client_ip},
                )
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail="Account locked",
                )
        except RedisError:
            pass
        # The per-address budget counts FAILED sign-ins only (issue 2007): a correct password is never rate limited,
        # so browsing the console (several authenticated requests per page) cannot lock the operator out, while
        # password guessing is still stopped after ADMIN_UI_RATE_LIMIT wrong attempts per window. A slot is reserved
        # with one atomic INCR before the (slow) password check, so a burst of concurrent guesses is counted at
        # once; the slot is handed back when the password turns out to be correct.
        try:
            reserved = redis_conn.incr(_rate_key(client_ip))
            if reserved == 1:
                redis_conn.expire(_rate_key(client_ip), rate_window)
            if reserved > rate_limit:
                redis_conn.decr(_rate_key(client_ip))
                log_event(
                    credentials.username,
                    "admin_ui_auth_rate_limited",
                    {"ip": client_ip},
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many failed sign-ins. Try again in a minute.",
                    headers={"Retry-After": str(rate_window)},
                )
            rate_slot = True
        except RedisError:
            pass

    username = os.getenv("ADMIN_UI_USERNAME", "admin")
    raw_hash = _get_active_password_hash(redis_conn, username)
    if not raw_hash:  # pragma: no cover - defensive
        raise RuntimeError(
            "ADMIN_UI_PASSWORD_HASH (or ADMIN_UI_PASSWORD_HASH_FILE) must be set",
        )
    password_hash = raw_hash.encode()
    headers = {"WWW-Authenticate": "Basic"}
    valid = secrets.compare_digest(credentials.username, username) and bcrypt.checkpw(
        credentials.password.encode(), password_hash
    )
    if not valid:
        LOGIN_ATTEMPTS.labels(result="failure").inc()
        _record_failed_attempt(redis_conn, credentials.username)
        log_event(
            credentials.username,
            "admin_ui_auth_failed",
            {"ip": client_ip},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers=headers)
    LOGIN_ATTEMPTS.labels(result="success").inc()
    if rate_slot:
        _release_rate_slot(redis_conn, client_ip)
    if request is not None:
        request.state.admin_ui_auth_provider = "basic"
        request.state.admin_ui_roles = {ADMIN_UI_ROLE}

    return _require_mfa(
        request,
        response,
        redis_conn,
        credentials.username,
        session_user,
        x_2fa_code,
        x_2fa_token,
        x_2fa_backup_code,
        force=_admin_ui_mfa_required(),
    )


def require_auth(
    request: Request,
    response: Response,
    credentials: HTTPBasicCredentials | None = Depends(security),
    x_2fa_code: str | None = Header(None, alias="X-2FA-Code"),
    x_2fa_token: str | None = Header(None, alias="X-2FA-Token"),
    x_2fa_backup_code: str | None = Header(None, alias="X-2FA-Backup-Code"),
    client_ip: str | None = None,
) -> str:
    """Validate HTTP Basic credentials, SSO, and optional 2FA."""
    return _require_auth_core(
        request,
        response,
        credentials,
        x_2fa_code,
        x_2fa_token,
        x_2fa_backup_code,
        client_ip,
    )


def _is_https_request(request: Request | None) -> bool:
    if os.getenv("ENABLE_HTTPS", "false").strip().lower() == "true":
        return True
    if request is None:
        return False
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )


def _session_cookie_secure(request: Request | None) -> bool:
    if os.getenv("ADMIN_UI_ALLOW_INSECURE_HTTP", "false").strip().lower() == "true":
        return _is_https_request(request)
    return True


def _set_session_cookie(
    response: Response | None,
    request: Request | None,
    redis_conn,
    username: str,
) -> None:
    if SESSION_TTL <= 0:
        return
    session_id = _issue_session(redis_conn, username)
    if not session_id:
        return
    if request is not None:
        request.state.admin_ui_session_cookie = session_id
        request.state.admin_ui_session_ttl = SESSION_TTL
    if response is not None:
        response.set_cookie(
            SESSION_COOKIE_NAME,
            session_id,
            max_age=SESSION_TTL,
            httponly=True,
            secure=_session_cookie_secure(request),
            samesite=SESSION_COOKIE_SAMESITE,
            path=SESSION_COOKIE_PATH,
        )


def require_admin(request: Request, user: str = Depends(require_auth)) -> str:
    """Ensure the authenticated user has admin privileges."""
    provider = getattr(request.state, "admin_ui_auth_provider", "basic")
    roles = getattr(request.state, "admin_ui_roles", set())
    if provider == "oidc":
        required_role = os.getenv("ADMIN_UI_OIDC_ADMIN_ROLE", "admin")
        is_admin = required_role in roles
    elif provider == "saml":
        required_role = os.getenv(
            "ADMIN_UI_SAML_ADMIN_GROUP",
            os.getenv("ADMIN_UI_SAML_REQUIRED_GROUP", "admin"),
        )
        is_admin = required_role in roles
    else:
        is_admin = ADMIN_UI_ROLE == "admin"
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


class PasskeyRegisterRequest(BaseModel):
    credential: dict | None = None


class PasskeyLoginRequest(BaseModel):
    username: str | None = None
    credential: dict | None = None


@router.post("/passkey/register")
async def passkey_register(
    data: PasskeyRegisterRequest = Body(...), user: str = Depends(require_auth)
):
    """Begin or complete passkey registration for the authenticated user."""
    if data.credential is not None:
        return passkeys.complete_registration({"credential": data.credential}, user)
    return passkeys.begin_registration(user)


@router.post("/passkey/login")
async def passkey_login(data: PasskeyLoginRequest = Body(...)):
    """Begin or complete passkey login and return a token on success."""
    if data.credential is not None:
        return passkeys.complete_login(
            {"username": data.username, "credential": data.credential}
        )
    if not data.username:
        raise HTTPException(status_code=422, detail="Username required")
    return passkeys.begin_login(data.username)


def require_csrf(request: Request) -> None:
    """Require X-CSRF-Token to equal the csrf_token cookie on state-changing calls.

    The admin API accepts Basic credentials, which browsers resend on cross-site requests.
    """
    cookie = request.cookies.get("csrf_token")
    header = request.headers.get("X-CSRF-Token")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


@router.post("/mfa/backup-codes")
async def generate_backup_codes(
    request: Request, response: Response, user: str = Depends(require_admin)
):
    """Generate and store new backup codes for MFA.

    Regenerating invalidates every earlier code, so the call needs the CSRF token. The new codes are
    shown once and must never be cached.
    """
    require_csrf(request)
    codes = mfa.generate_backup_codes()
    if not mfa.store_backup_codes(user, codes):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backup codes unavailable",
        )
    response.headers["Cache-Control"] = "no-store"
    log_event(user, "regenerate_backup_codes", {"count": len(codes)})
    return {"backup_codes": codes}


@router.get("/mfa/backup-codes/remaining")
async def backup_codes_remaining(user: str = Depends(require_admin)):
    """Return the number of remaining backup codes."""
    remaining = mfa.get_remaining_backup_codes_count(user)
    return {"remaining": remaining}


def _password_override_key(username: str) -> str:
    return f"admin_ui:auth:password_hash:{username}"


def _get_active_password_hash(redis_conn, username: str) -> str | None:
    if redis_conn:
        try:
            raw = redis_conn.get(_password_override_key(username))
            if raw:
                return _decode_redis(raw)
        except RedisError:
            pass
    return get_secret("ADMIN_UI_PASSWORD_HASH_FILE") or os.environ.get(
        "ADMIN_UI_PASSWORD_HASH"
    )


class TotpVerifyPayload(BaseModel):
    code: str


class ChangePasswordPayload(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


@router.post("/mfa/totp/setup")
async def setup_totp(
    request: Request,
    user: str = Depends(require_auth),
):
    """Begin self-service TOTP enrollment and return QR matrix + secret."""
    require_csrf(request)
    try:
        payload = mfa.begin_totp_enrollment(user)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    log_event(user, "admin_ui_totp_setup_started", {})
    return payload


@router.post("/mfa/totp/verify")
async def verify_totp_enrollment(
    request: Request,
    payload: TotpVerifyPayload,
    user: str = Depends(require_auth),
):
    """Verify a 6-digit TOTP code to activate authenticator enrollment."""
    require_csrf(request)
    if not mfa.complete_totp_enrollment(user, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )
    log_event(user, "admin_ui_totp_enrolled", {})
    return {"status": "ok", "totp_enabled": True}


def _validate_password_change_request(
    request: Request, payload: ChangePasswordPayload
) -> None:
    if getattr(request.state, "admin_ui_auth_provider", "basic") in {"oidc", "saml"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password is managed by your single sign-on provider",
        )
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation do not match",
        )
    if len(payload.new_password) < 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 12 characters",
        )


@router.post("/account/password")
async def change_password(
    request: Request,
    payload: ChangePasswordPayload,
    user: str = Depends(require_auth),
):
    """Allow an authenticated local admin to change their own password."""
    require_csrf(request)
    _validate_password_change_request(request, payload)
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable, cannot update password",
        )
    active_hash = _get_active_password_hash(redis_conn, user)
    if not active_hash or not bcrypt.checkpw(
        payload.current_password.encode(), active_hash.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
    new_hash = bcrypt.hashpw(payload.new_password.encode(), bcrypt.gensalt()).decode()
    try:
        redis_conn.set(_password_override_key(user), new_hash)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to persist new password",
        ) from exc
    if "ADMIN_UI_PASSWORD_HASH" in os.environ:
        os.environ["ADMIN_UI_PASSWORD_HASH"] = new_hash
    log_event(user, "admin_ui_password_changed", {})
    return {"status": "ok"}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    user: str = Depends(require_auth),
):
    """Invalidate the current Admin UI session cookie."""
    redis_conn = get_redis_connection()
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    _clear_session(redis_conn, session_id)
    # Browsers only delete cookies when the attributes match (path/samesite/secure).
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path=SESSION_COOKIE_PATH,
        secure=_session_cookie_secure(request),
        httponly=True,
        samesite=SESSION_COOKIE_SAMESITE,
    )
    return {"status": "ok"}
