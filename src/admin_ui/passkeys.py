import json
import os
import time
from base64 import b64decode, b64encode
from json import JSONDecodeError
from uuid import uuid4

from fastapi import HTTPException
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

PASSKEY_TOKEN_TTL = 300

RP_ID = os.getenv("WEBAUTHN_RP_ID", "localhost")
ORIGIN = os.getenv("WEBAUTHN_ORIGIN", "http://localhost")


def _cred_key(user: str) -> str:
    return tenant_key(f"passkey:cred:{user}")


def _challenge_key(user: str) -> str:
    return tenant_key(f"passkey:challenge:{user}")


def _token_key(token: str) -> str:
    return tenant_key(f"passkey:token:{token}")


def _store_credential(user: str, cred: dict) -> None:
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    redis_conn.set(_cred_key(user), json.dumps(cred))


def _load_credential(user: str) -> dict | None:
    redis_conn = get_redis_connection()
    if not redis_conn:
        return None
    raw = redis_conn.get(_cred_key(user))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except JSONDecodeError:
        return None


def _store_challenge(user: str, challenge: bytes) -> None:
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    redis_conn.set(
        _challenge_key(user),
        b64encode(challenge).decode(),
        ex=PASSKEY_TOKEN_TTL,
    )


def _consume_challenge(user: str) -> bytes | None:
    redis_conn = get_redis_connection()
    if not redis_conn:
        return None
    raw = redis_conn.getdel(_challenge_key(user))
    return b64decode(raw) if raw else None


def _store_passkey_token(token: str, user: str, exp: float | None = None) -> None:
    if exp is None:
        exp = time.time() + PASSKEY_TOKEN_TTL
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    ttl = max(int(exp - time.time()), 1)
    redis_conn.set(_token_key(token), user, ex=ttl)


def _consume_passkey_token(token: str | None) -> str | None:
    if not token:
        return None
    redis_conn = get_redis_connection()
    if not redis_conn:
        return None
    return redis_conn.getdel(_token_key(token))


def _has_passkey_tokens() -> bool:
    redis_conn = get_redis_connection()
    if not redis_conn:
        return False
    return next(redis_conn.scan_iter(_token_key("*"), count=1), None) is not None


def begin_registration(user: str) -> JSONResponse:
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name="AI Scraping Defense",
        user_id=user.encode(),
        user_name=user,
    )
    _store_challenge(user, options.challenge)
    return JSONResponse(json.loads(options_to_json(options)))


def complete_registration(data: dict, user: str) -> JSONResponse:
    credential = RegistrationCredential.parse_raw(json.dumps(data["credential"]))
    challenge = _consume_challenge(user)
    if not challenge:
        raise HTTPException(status_code=400, detail="Challenge expired")
    verification = verify_registration_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
    )
    _store_credential(
        user,
        {
            "credential_id": verification.credential_id,
            "public_key": verification.credential_public_key,
            "sign_count": verification.sign_count,
        },
    )
    return JSONResponse({"status": "ok"})


def begin_login(username: str) -> JSONResponse:
    cred = _load_credential(username)
    if not cred:
        raise HTTPException(status_code=400, detail="Unknown user")
    descriptor = PublicKeyCredentialDescriptor(id=cred["credential_id"])
    options = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=[descriptor],
    )
    _store_challenge(username, options.challenge)
    return JSONResponse(json.loads(options_to_json(options)))


def complete_login(data: dict) -> JSONResponse:
    username = data.get("username")
    if not isinstance(username, str) or not username:
        raise HTTPException(status_code=400, detail="Invalid or missing username")
    cred = _load_credential(username)
    if not cred:
        raise HTTPException(status_code=400, detail="Unknown user")
    challenge = _consume_challenge(username)
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
    _store_credential(username, cred)
    token = uuid4().hex
    _store_passkey_token(token, username)
    return JSONResponse({"token": token})
