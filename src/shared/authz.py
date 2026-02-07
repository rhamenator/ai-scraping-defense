import os
from pathlib import Path
from typing import Iterable, Optional

from fastapi import HTTPException, Request, status

try:
    import jwt
    from jwt import InvalidTokenError
except Exception:  # pragma: no cover - dependency missing in some envs
    jwt = None  # type: ignore
    InvalidTokenError = Exception  # type: ignore


ALGORITHMS_ALLOWED = {
    "HS256",
    "HS384",
    "HS512",
    "RS256",
    "RS384",
    "RS512",
    "ES256",
    "ES384",
    "ES512",
    "EdDSA",
}
ALGORITHMS_DEFAULT = [
    alg.strip()
    for alg in os.getenv("AUTH_JWT_ALGORITHMS", "HS256").split(",")
    if alg.strip()
]
ALGORITHMS_DEFAULT = [alg for alg in ALGORITHMS_DEFAULT if alg in ALGORITHMS_ALLOWED]
JWT_SECRET = os.getenv("AUTH_JWT_SECRET")
JWT_ISSUER = os.getenv("AUTH_JWT_ISSUER")
JWT_AUDIENCE = os.getenv("AUTH_JWT_AUDIENCE")
JWT_SECRET_FILE = os.getenv("AUTH_JWT_SECRET_FILE")
JWT_PUBLIC_KEY = os.getenv("AUTH_JWT_PUBLIC_KEY")
JWT_PUBLIC_KEY_FILE = os.getenv("AUTH_JWT_PUBLIC_KEY_FILE")


def _read_secret_file(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return Path(path).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _is_hmac_algorithm(alg: str) -> bool:
    return alg.upper().startswith("HS")


def _looks_like_pem(value: str) -> bool:
    return value.strip().startswith("-----BEGIN")


def _jwt_verification_key(algorithms: list[str]) -> str | None:
    """Return the key material to verify JWT signatures.

    For HMAC (HS*) algorithms this uses AUTH_JWT_SECRET / AUTH_JWT_SECRET_FILE.
    For asymmetric algorithms (RS*/ES*/EdDSA) this uses AUTH_JWT_PUBLIC_KEY /
    AUTH_JWT_PUBLIC_KEY_FILE, with a compatibility fallback to AUTH_JWT_SECRET if
    it looks like a PEM key.
    """

    algs = [a.strip() for a in algorithms if a.strip()]
    if not algs:
        return None

    uses_hs = any(_is_hmac_algorithm(a) for a in algs)
    uses_asym = any(not _is_hmac_algorithm(a) for a in algs)
    if uses_hs and uses_asym:
        # Ambiguous and likely misconfigured.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT algorithms mix HMAC and asymmetric types",
        )

    if uses_hs:
        return JWT_SECRET or _read_secret_file(JWT_SECRET_FILE)

    # Asymmetric: prefer explicit public key vars.
    return (
        JWT_PUBLIC_KEY
        or _read_secret_file(JWT_PUBLIC_KEY_FILE)
        or (JWT_SECRET if JWT_SECRET and _looks_like_pem(JWT_SECRET) else None)
    )


def _extract_bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    return auth.split(" ", 1)[1].strip() or None


def _roles_from_claims(claims: dict) -> set[str]:
    roles: set[str] = set()
    # Common patterns: roles claim (list of strings), scope/scopes space-separated
    if isinstance(claims.get("roles"), (list, tuple)):
        roles.update(str(r) for r in claims["roles"])
    if isinstance(claims.get("scope"), str):
        roles.update(claims["scope"].split())
    if isinstance(claims.get("scopes"), str):
        roles.update(claims["scopes"].split())
    return roles


def verify_jwt_from_request(
    request: Request,
    required_roles: Optional[Iterable[str]] = None,
    *,
    raise_on_missing: bool = True,
) -> dict:
    if jwt is None:
        if raise_on_missing:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="JWT auth not configured",
            )
        return {}
    if not ALGORITHMS_DEFAULT:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT algorithms not configured",
        )
    key = _jwt_verification_key(ALGORITHMS_DEFAULT)
    if not key:
        if raise_on_missing:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="JWT auth not configured",
            )
        return {}
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token"
        )
    try:
        options = {"require": ["exp", "iat"]}
        claims = jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS_DEFAULT,
            audience=JWT_AUDIENCE if JWT_AUDIENCE else None,
            issuer=JWT_ISSUER if JWT_ISSUER else None,
            options=options,
        )
    except InvalidTokenError as exc:  # pragma: no cover - runtime validation
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

    if required_roles:
        assigned = _roles_from_claims(claims)
        if not any(r in assigned for r in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
    return claims


def require_jwt(
    required_roles: Optional[Iterable[str]] = None, *, optional: bool = False
):
    async def _dep(request: Request):
        return verify_jwt_from_request(
            request, required_roles, raise_on_missing=not optional
        )

    return _dep
