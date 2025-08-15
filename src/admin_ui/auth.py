import os
import secrets

import bcrypt
import pyotp
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from src.shared.config import get_secret

security = HTTPBasic()

ADMIN_UI_ROLE = os.getenv("ADMIN_UI_ROLE", "admin")


def require_auth(
    credentials: HTTPBasicCredentials = Depends(security),
    x_2fa_code: str | None = Header(None, alias="X-2FA-Code"),
    x_2fa_token: str | None = Header(None, alias="X-2FA-Token"),
) -> str:
    """Validate HTTP Basic credentials and optional 2FA."""
    from . import webauthn

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

    token_valid = x_2fa_token in webauthn.VALID_WEBAUTHN_TOKENS
    token_user = webauthn._consume_webauthn_token(x_2fa_token)
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
    if webauthn.VALID_WEBAUTHN_TOKENS and not token_valid:
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
