import os
from typing import Iterable, Optional

from fastapi import Depends, HTTPException, Request, status

try:
    import jwt
    from jwt import InvalidTokenError
except Exception as exc:  # pragma: no cover - dependency missing in some envs
    jwt = None  # type: ignore
    InvalidTokenError = Exception  # type: ignore


ALGORITHMS_DEFAULT = [alg.strip() for alg in os.getenv("AUTH_JWT_ALGORITHMS", "HS256").split(",") if alg.strip()]
JWT_SECRET = os.getenv("AUTH_JWT_SECRET")
JWT_ISSUER = os.getenv("AUTH_JWT_ISSUER")
JWT_AUDIENCE = os.getenv("AUTH_JWT_AUDIENCE")


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
    request: Request, required_roles: Optional[Iterable[str]] = None
) -> dict:
    if jwt is None or not JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT auth not configured",
        )
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token"
        )
    try:
        options = {"require": ["exp", "iat"]}
        claims = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=ALGORITHMS_DEFAULT,
            audience=JWT_AUDIENCE if JWT_AUDIENCE else None,
            issuer=JWT_ISSUER if JWT_ISSUER else None,
            options=options,
        )
    except InvalidTokenError as exc:  # pragma: no cover - runtime validation
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    if required_roles:
        assigned = _roles_from_claims(claims)
        if not any(r in assigned for r in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
    return claims


def require_jwt(required_roles: Optional[Iterable[str]] = None):
    async def _dep(request: Request):
        return verify_jwt_from_request(request, required_roles)

    return _dep

