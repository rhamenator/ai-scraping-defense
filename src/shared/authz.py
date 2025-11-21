import os
from typing import Iterable, Optional

from fastapi import HTTPException, Request, status

try:
    import jwt
    from jwt import InvalidTokenError
except Exception:  # pragma: no cover - dependency missing in some envs
    jwt = None  # type: ignore
    InvalidTokenError = Exception  # type: ignore

try:
    from src.security.mobile_security import MobilePlatform
except ImportError:  # pragma: no cover - optional dependency
    MobilePlatform = None  # type: ignore


ALGORITHMS_DEFAULT = [
    alg.strip()
    for alg in os.getenv("AUTH_JWT_ALGORITHMS", "HS256").split(",")
    if alg.strip()
]
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


def _validate_mobile_claims(claims: dict, request: Request) -> None:
    """Validate mobile-specific JWT claims.

    Mobile JWTs should include:
    - 'mobile_platform': Platform identifier (ios, android, etc.)
    - 'app_version': Application version
    - 'device_id': Unique device identifier (optional)
    """
    # Check if this is a mobile request
    if not hasattr(request.state, "mobile_device_info"):
        return  # Not a mobile request, skip validation

    mobile_platform = claims.get("mobile_platform")
    app_version = claims.get("app_version")

    # Validate mobile platform claim exists
    if not mobile_platform:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mobile platform claim missing in token",
        )

    # Validate platform matches the detected platform
    device_info = request.state.mobile_device_info
    if MobilePlatform and device_info.platform != MobilePlatform.UNKNOWN:
        expected_platform = device_info.platform.value
        if mobile_platform != expected_platform:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Mobile platform mismatch",
            )

    # Warn if app version is missing
    if not app_version:
        # Not a hard failure, but should be logged
        pass


def verify_jwt_from_request(
    request: Request,
    required_roles: Optional[Iterable[str]] = None,
    *,
    raise_on_missing: bool = True,
    validate_mobile: bool = True,
) -> dict:
    if jwt is None or not JWT_SECRET:
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

    # Validate mobile-specific claims if this is a mobile request
    if validate_mobile:
        _validate_mobile_claims(claims, request)

    return claims


def require_jwt(
    required_roles: Optional[Iterable[str]] = None,
    *,
    optional: bool = False,
    validate_mobile: bool = True,
):
    async def _dep(request: Request):
        return verify_jwt_from_request(
            request,
            required_roles,
            raise_on_missing=not optional,
            validate_mobile=validate_mobile,
        )

    return _dep
