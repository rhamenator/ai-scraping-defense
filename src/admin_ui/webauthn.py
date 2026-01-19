import json
import os
import time
from base64 import b64decode, b64encode
from json import JSONDecodeError
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticationCredential,
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    RegistrationCredential,
)

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

from .auth import require_auth

router = APIRouter()

WEBAUTHN_TOKEN_TTL = int(os.getenv("WEBAUTHN_TOKEN_TTL", "300"))
MAX_USERNAME_LENGTH = int(os.getenv("ADMIN_UI_USERNAME_MAX_LENGTH", "128"))

RP_ID = os.getenv("WEBAUTHN_RP_ID", "localhost")
ORIGIN = os.getenv("WEBAUTHN_ORIGIN", "http://localhost")


def _cred_key(user: str) -> str:
    return tenant_key(f"webauthn:cred:{user}")


def _token_key(token: str) -> str:
    return tenant_key(f"webauthn:token:{token}")


def _challenge_key(user: str) -> str:
    return tenant_key(f"webauthn:challenge:{user}")


def _store_webauthn_credential(user: str, cred: dict) -> None:
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    redis_conn.set(_cred_key(user), json.dumps(cred))


def _load_webauthn_credential(user: str) -> dict | None:
    redis_conn = get_redis_connection()
    if not redis_conn:
        return None
    raw = redis_conn.get(_cred_key(user))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except JSONDecodeError:
        # Treat corrupted data as missing; user can re-register
        return None


def _store_webauthn_challenge(user: str, challenge: bytes) -> None:
    """Persist a WebAuthn challenge for later verification."""
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    redis_conn.set(
        _challenge_key(user), b64encode(challenge).decode(), ex=WEBAUTHN_TOKEN_TTL
    )


def _consume_webauthn_challenge(user: str) -> bytes | None:
    redis_conn = get_redis_connection()
    if not redis_conn:
        return None
    raw = redis_conn.getdel(_challenge_key(user))
    return b64decode(raw) if raw else None


def _store_webauthn_token(token: str, user: str, exp: float | None = None) -> None:
    """Persist a WebAuthn login token with an optional expiry timestamp."""
    if exp is None:
        exp = time.time() + WEBAUTHN_TOKEN_TTL
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    ttl = max(int(exp - time.time()), 1)
    redis_conn.set(_token_key(token), user, ex=ttl)


def _consume_webauthn_token(token: str | None) -> str | None:
    if not token:
        return None
    redis_conn = get_redis_connection()
    if not redis_conn:
        return None
    return redis_conn.getdel(_token_key(token))


def _has_webauthn_tokens() -> bool:
    redis_conn = get_redis_connection()
    if not redis_conn:
        return False
    return next(redis_conn.scan_iter(_token_key("*"), count=1), None) is not None


def _authenticator_selection() -> AuthenticatorSelectionCriteria | None:
    preference = os.getenv("WEBAUTHN_AUTHENTICATOR_ATTACHMENT", "none").strip().lower()
    if preference == "platform":
        return AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM
        )
    if preference == "cross-platform":
        return AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.CROSS_PLATFORM
        )
    return None


def _login_error() -> HTTPException:
    return HTTPException(status_code=400, detail="Invalid login request")


def _validate_username(username: str, *, detail: str) -> None:
    if not isinstance(username, str) or not username:
        raise HTTPException(status_code=400, detail=detail)
    if len(username) > MAX_USERNAME_LENGTH:
        raise HTTPException(status_code=400, detail=detail)


@router.post("/webauthn/register/begin")
async def webauthn_register_begin(user: str = Depends(require_auth)):
    """Begin WebAuthn registration and return options."""
    _validate_username(user, detail="Invalid or missing username")
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name="AI Scraping Defense",
        user_id=user.encode(),
        user_name=user,
        authenticator_selection=_authenticator_selection(),
    )
    _store_webauthn_challenge(user, options.challenge)
    return JSONResponse(json.loads(options_to_json(options)))


@router.post("/webauthn/register/complete")
async def webauthn_register_complete(data: dict, user: str = Depends(require_auth)):
    """Complete WebAuthn registration."""
    credential = RegistrationCredential.parse_raw(json.dumps(data["credential"]))
    challenge = _consume_webauthn_challenge(user)
    if not challenge:
        raise HTTPException(status_code=400, detail="Challenge expired")
    verification = verify_registration_response(
        credential=credential,
        expected_challenge=challenge,
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


@router.post("/webauthn/login/begin")
async def webauthn_login_begin(data: dict):
    """Begin WebAuthn authentication and return options."""
    username = data.get("username")
    _validate_username(username, detail="Invalid login request")
    cred = _load_webauthn_credential(username)

    if not cred:
        raise _login_error()
    descriptor = PublicKeyCredentialDescriptor(id=cred["credential_id"])
    options = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=[descriptor],
    )
    _store_webauthn_challenge(username, options.challenge)
    return JSONResponse(json.loads(options_to_json(options)))


@router.post("/webauthn/login/complete")
async def webauthn_login_complete(data: dict):
    """Complete WebAuthn authentication and return a token."""
    username = data.get("username")
    _validate_username(username, detail="Invalid login request")
    cred = _load_webauthn_credential(username)
    if not cred:
        raise _login_error()
    challenge = _consume_webauthn_challenge(username)
    if not challenge:
        raise HTTPException(status_code=400, detail="Challenge expired")
    credential = AuthenticationCredential.parse_raw(json.dumps(data["credential"]))
    verification = verify_authentication_response(
        credential=credential,
        expected_challenge=challenge,
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
