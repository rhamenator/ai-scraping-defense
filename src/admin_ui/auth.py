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

from . import mfa, passkeys

security = HTTPBasic()
router = APIRouter()

ADMIN_UI_ROLE = os.getenv("ADMIN_UI_ROLE", "admin")
LOCKOUT_THRESHOLD = int(os.getenv("ADMIN_UI_LOCKOUT_THRESHOLD", "5"))
LOCKOUT_DURATION = int(os.getenv("ADMIN_UI_LOCKOUT_DURATION", "900"))
SESSION_TTL = int(os.getenv("ADMIN_UI_SESSION_TTL", "3600"))
SESSION_MAX_CONCURRENT = int(os.getenv("ADMIN_UI_SESSION_MAX_CONCURRENT", "3"))
SESSION_COOKIE_NAME = os.getenv("ADMIN_UI_SESSION_COOKIE", "admin_ui_session")


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


def _require_auth_core(
    request: Request | None,
    response: Response | None,
    credentials: HTTPBasicCredentials,
    x_2fa_code: str | None,
    x_2fa_token: str | None,
    x_2fa_backup_code: str | None,
    client_ip: str | None,
) -> str:
    """Validate HTTP Basic credentials and optional 2FA."""
    from . import webauthn

    rate_limit = int(os.getenv("ADMIN_UI_RATE_LIMIT", "5"))
    rate_window = int(os.getenv("ADMIN_UI_RATE_LIMIT_WINDOW", "60"))
    if client_ip is None:
        if request is None or not request.client or not request.client.host:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot determine client IP address for rate limiting",
            )
        client_ip = request.client.host
    redis_conn = get_redis_connection()
    session_id = None
    session_user = None
    if request is not None:
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        session_user = _get_session_user(redis_conn, session_id)
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
        key = f"admin_ui:auth:{client_ip}"
        try:
            count = redis_conn.incr(key)
            if count == 1:
                redis_conn.expire(key, rate_window)
            if count > rate_limit:
                log_event(
                    credentials.username,
                    "admin_ui_auth_rate_limited",
                    {"ip": client_ip},
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many authentication attempts",
                )
        except RedisError:
            pass

    username = os.getenv("ADMIN_UI_USERNAME", "admin")
    try:
        password_hash = os.environ["ADMIN_UI_PASSWORD_HASH"].encode()
    except KeyError as exc:  # pragma: no cover - defensive
        raise RuntimeError(
            "ADMIN_UI_PASSWORD_HASH environment variable must be set",
        ) from exc
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

    token_user = passkeys._consume_passkey_token(
        x_2fa_token
    ) or webauthn._consume_webauthn_token(x_2fa_token)
    if token_user and token_user != credentials.username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA token",
            headers=headers,
        )

    totp_secret = os.getenv("ADMIN_UI_2FA_SECRET") or get_secret(
        "ADMIN_UI_2FA_SECRET_FILE"
    )
    session_valid = session_user == credentials.username
    if totp_secret:
        if token_user or session_valid:
            if redis_conn:
                redis_conn.delete(_failure_key(credentials.username))
            if not session_valid:
                _set_session_cookie(response, request, redis_conn, credentials.username)
            return credentials.username
        if x_2fa_code:
            totp = pyotp.TOTP(totp_secret)

            if totp.verify(x_2fa_code, valid_window=1):
                if redis_conn:
                    redis_conn.delete(_failure_key(credentials.username))
                _set_session_cookie(response, request, redis_conn, credentials.username)
                return credentials.username
            detail = "Invalid 2FA code"
        elif x_2fa_backup_code:
            if mfa.verify_backup_code(credentials.username, x_2fa_backup_code):
                if redis_conn:
                    redis_conn.delete(_failure_key(credentials.username))
                _set_session_cookie(response, request, redis_conn, credentials.username)
                return credentials.username
            detail = "Invalid backup code"
        else:
            detail = "2FA token, code, or backup code required"
        _record_failed_attempt(redis_conn, credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers=headers
        )

    if token_user or session_valid:
        if redis_conn:
            redis_conn.delete(_failure_key(credentials.username))
        if not session_valid:
            _set_session_cookie(response, request, redis_conn, credentials.username)
        return credentials.username
    if (
        passkeys._has_passkey_tokens() or webauthn._has_webauthn_tokens()
    ) and not token_user:
        _record_failed_attempt(redis_conn, credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="2FA token required",
            headers=headers,
        )
    if redis_conn:
        redis_conn.delete(_failure_key(credentials.username))
    _set_session_cookie(response, request, redis_conn, credentials.username)
    return credentials.username


def require_auth(
    request: Request,
    response: Response,
    credentials: HTTPBasicCredentials = Depends(security),
    x_2fa_code: str | None = Header(None, alias="X-2FA-Code"),
    x_2fa_token: str | None = Header(None, alias="X-2FA-Token"),
    x_2fa_backup_code: str | None = Header(None, alias="X-2FA-Backup-Code"),
    client_ip: str | None = None,
) -> str:
    """Validate HTTP Basic credentials and optional 2FA."""
    return _require_auth_core(
        request,
        response,
        credentials,
        x_2fa_code,
        x_2fa_token,
        x_2fa_backup_code,
        client_ip,
    )


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
            secure=True,
            samesite="Strict",
        )


def require_admin(user: str = Depends(require_auth)) -> str:
    """Ensure the authenticated user has admin privileges."""
    if ADMIN_UI_ROLE != "admin":
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


@router.post("/mfa/backup-codes")
async def generate_backup_codes(user: str = Depends(require_admin)):
    """Generate and store new backup codes for MFA."""
    codes = mfa.generate_backup_codes()
    if not mfa.store_backup_codes(user, codes):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backup codes unavailable",
        )
    return {"backup_codes": codes}


@router.get("/mfa/backup-codes/remaining")
async def backup_codes_remaining(user: str = Depends(require_admin)):
    """Return the number of remaining backup codes."""
    remaining = mfa.get_remaining_backup_codes_count(user)
    return {"remaining": remaining}


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
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "ok"}
