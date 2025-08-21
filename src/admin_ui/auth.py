import os
import secrets

import bcrypt
import pyotp
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from redis.exceptions import RedisError

from src.shared.config import get_secret
from src.shared.redis_client import get_redis_connection

from . import passkeys

security = HTTPBasic()
router = APIRouter()

ADMIN_UI_ROLE = os.getenv("ADMIN_UI_ROLE", "admin")


def require_auth(
    request: Request = None,
    credentials: HTTPBasicCredentials = Depends(security),
    x_2fa_code: str | None = Header(None, alias="X-2FA-Code"),
    x_2fa_token: str | None = Header(None, alias="X-2FA-Token"),
    client_ip: str | None = None,
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
    if redis_conn:
        key = f"admin_ui:auth:{client_ip}"
        try:
            count = redis_conn.incr(key)
            if count == 1:
                redis_conn.expire(key, rate_window)
            if count > rate_limit:
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers=headers)

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
    if totp_secret:
        if token_user:
            return credentials.username
        if x_2fa_code:
            totp = pyotp.TOTP(totp_secret)

            if totp.verify(x_2fa_code, valid_window=1):
                return credentials.username
            detail = "Invalid 2FA code"
        else:
            detail = "2FA token or code required"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers=headers
        )

    if token_user:
        return credentials.username
    if (
        passkeys._has_passkey_tokens() or webauthn._has_webauthn_tokens()
    ) and not token_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="2FA token required",
            headers=headers,
        )
    return credentials.username


def require_admin(user: str = Depends(require_auth)) -> str:
    """Ensure the authenticated user has admin privileges."""
    if ADMIN_UI_ROLE != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


@router.post("/passkey/register")
async def passkey_register(data: dict | None = None, user: str = Depends(require_auth)):
    """Begin or complete passkey registration for the authenticated user."""
    payload = data or {}
    if "credential" in payload:
        return passkeys.complete_registration(payload, user)
    return passkeys.begin_registration(user)


@router.post("/passkey/login")
async def passkey_login(data: dict):
    """Begin or complete passkey login and return a token on success."""
    if "credential" in data:
        return passkeys.complete_login(data)
    username = data.get("username")
    if not isinstance(username, str) or not username:
        raise HTTPException(status_code=400, detail="Invalid or missing username")
    return passkeys.begin_login(username)
