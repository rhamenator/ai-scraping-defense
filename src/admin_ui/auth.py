import os
import secrets

import bcrypt
import pyotp
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from redis.exceptions import RedisError

from src.shared.config import get_secret
from src.shared.redis_client import get_redis_connection

from . import mfa, passkeys

security = HTTPBasic()
router = APIRouter()

ADMIN_UI_ROLE = os.getenv("ADMIN_UI_ROLE", "admin")


def require_auth(
    request: Request = None,
    credentials: HTTPBasicCredentials = Depends(security),
    x_2fa_code: str | None = Header(None, alias="X-2FA-Code"),
    x_2fa_token: str | None = Header(None, alias="X-2FA-Token"),
    x_2fa_backup_code: str | None = Header(None, alias="X-2FA-Backup-Code"),
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
        elif x_2fa_backup_code:
            if mfa.verify_backup_code(credentials.username, x_2fa_backup_code):
                return credentials.username
            detail = "Invalid backup code"
        else:
            detail = "2FA token, code, or backup code required"
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
