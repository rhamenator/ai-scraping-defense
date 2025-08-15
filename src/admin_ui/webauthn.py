import json
import os
import time
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
    PublicKeyCredentialDescriptor,
    RegistrationCredential,
)

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

from .auth import require_auth

router = APIRouter()

WEBAUTHN_CREDENTIALS: dict[str, dict] = {}
WEBAUTHN_CHALLENGES: dict[str, tuple[bytes, float]] = {}
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


def _cleanup_expired_webauthn_challenges() -> None:
    """Remove expired challenges from the in-memory store."""
    now = time.time()
    expired = [
        user
        for user, (_, ts) in WEBAUTHN_CHALLENGES.items()
        if now - ts > WEBAUTHN_TOKEN_TTL
    ]
    for user in expired:
        WEBAUTHN_CHALLENGES.pop(user, None)


def _store_webauthn_challenge(user: str, challenge: bytes) -> None:
    """Persist a WebAuthn challenge for later verification."""
    redis_conn = get_redis_connection()
    if redis_conn:
        key = tenant_key(f"webauthn:challenge:{user}")
        redis_conn.set(key, challenge, ex=WEBAUTHN_TOKEN_TTL)
    else:
        _cleanup_expired_webauthn_challenges()
        WEBAUTHN_CHALLENGES[user] = (challenge, time.time())


def _store_webauthn_token(token: str, user: str, exp: float | None = None) -> None:
    """Persist a WebAuthn login token with an optional expiry timestamp."""
    if exp is None:
        exp = time.time() + WEBAUTHN_TOKEN_TTL
    redis_conn = get_redis_connection()
    if redis_conn:
        ttl = max(int(exp - time.time()), 1)
        redis_conn.set(_token_key(token), user, ex=ttl)
    else:
        VALID_WEBAUTHN_TOKENS[token] = (user, exp)


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


@router.post("/webauthn/register/begin")
async def webauthn_register_begin(user: str = Depends(require_auth)):
    """Begin WebAuthn registration and return options."""
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name="AI Scraping Defense",
        user_id=user.encode(),
        user_name=user,
    )
    _store_webauthn_challenge(user, options.challenge)
    return JSONResponse(json.loads(options_to_json(options)))


@router.post("/webauthn/register/complete")
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


@router.post("/webauthn/login/begin")
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
    _store_webauthn_challenge(username, options.challenge)
    return JSONResponse(json.loads(options_to_json(options)))


@router.post("/webauthn/login/complete")
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
