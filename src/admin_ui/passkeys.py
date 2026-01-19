import json
import logging
import math
import os
import time
from base64 import b64decode, b64encode
from json import JSONDecodeError
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
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

PASSKEY_TOKEN_TTL = int(os.getenv("PASSKEY_TOKEN_TTL", "300"))
MAX_USERNAME_LENGTH = int(os.getenv("ADMIN_UI_USERNAME_MAX_LENGTH", "128"))

RP_ID = os.getenv("WEBAUTHN_RP_ID", "localhost")
ORIGIN = os.getenv("WEBAUTHN_ORIGIN", "http://localhost")


logger = logging.getLogger(__name__)


JSON_SERIALIZATION_PARAMS = {"separators": (",", ":"), "sort_keys": True}


_ENC_KEY: bytes | None = None


def _get_enc_key() -> bytes:
    """Return the AES-GCM key from PASSKEYS_ENC_KEY env var."""
    global _ENC_KEY
    if _ENC_KEY is not None:
        return _ENC_KEY
    key_b64 = os.getenv("PASSKEYS_ENC_KEY")
    if not key_b64:
        raise RuntimeError("PASSKEYS_ENC_KEY environment variable must be set")
    try:
        key = b64decode(key_b64)
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError("PASSKEYS_ENC_KEY must be base64-encoded") from exc
    if len(key) != 32:
        raise RuntimeError("PASSKEYS_ENC_KEY must decode to 32 bytes")
    _ENC_KEY = key
    return key


def _login_error() -> HTTPException:
    return HTTPException(status_code=400, detail="Invalid login request")


def _validate_username(username: str, *, detail: str) -> None:
    if not isinstance(username, str) or not username:
        raise HTTPException(status_code=400, detail=detail)
    if len(username) > MAX_USERNAME_LENGTH:
        raise HTTPException(status_code=400, detail=detail)


def encrypt_json(obj: dict) -> str:
    """Encrypt a JSON-serializable dict and return base64 payload."""
    payload = json.dumps(obj, **JSON_SERIALIZATION_PARAMS).encode()
    aes = AESGCM(_get_enc_key())
    nonce = os.urandom(12)
    cipher = aes.encrypt(nonce, payload, None)
    return b64encode(nonce + cipher).decode()


def decrypt_json(data: str) -> dict:
    """Decrypt base64 payload produced by encrypt_json."""
    raw = b64decode(data)
    if len(raw) < 12:
        raise ValueError("Invalid ciphertext")
    nonce, cipher = raw[:12], raw[12:]
    aes = AESGCM(_get_enc_key())
    plain = aes.decrypt(nonce, cipher, None)
    return json.loads(plain)


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
    redis_conn.set(_cred_key(user), encrypt_json(cred))


def _load_credential(user: str) -> dict | None:
    redis_conn = get_redis_connection()
    if not redis_conn:
        return None
    raw = redis_conn.get(_cred_key(user))
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        return decrypt_json(raw)
    except Exception:
        try:
            cred = json.loads(raw)
            logger.warning("Stored passkey credential for %s is plaintext", user)
            return cred
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
    """Persist a login token with an expiration time."""
    now = time.time()
    if exp is None:
        exp = now + PASSKEY_TOKEN_TTL
    elif exp <= now:
        raise ValueError("Cannot store passkey token: expiration time is in the past")
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise RuntimeError("Redis unavailable")
    ttl = max(1, math.ceil(exp - now))
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
    _validate_username(user, detail="Invalid or missing username")
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
    _validate_username(username, detail="Invalid login request")
    cred = _load_credential(username)
    if not cred:
        raise _login_error()
    descriptor = PublicKeyCredentialDescriptor(id=cred["credential_id"])
    options = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=[descriptor],
    )
    _store_challenge(username, options.challenge)
    return JSONResponse(json.loads(options_to_json(options)))


def complete_login(data: dict) -> JSONResponse:
    username = data.get("username")
    _validate_username(username, detail="Invalid login request")
    cred = _load_credential(username)
    if not cred:
        raise _login_error()
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
