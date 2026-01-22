import os
from typing import Any, Optional

from fastapi import HTTPException, Request, status

from src.shared.authz import _roles_from_claims
from src.shared.config import get_secret

try:
    import jwt
    from jwt import InvalidTokenError
except Exception:  # pragma: no cover - dependency missing in some envs
    jwt = None  # type: ignore
    InvalidTokenError = Exception  # type: ignore


def _sso_enabled() -> bool:
    return os.getenv("ADMIN_UI_SSO_ENABLED", "false").lower() == "true"


def _sso_mode() -> str:
    return os.getenv("ADMIN_UI_SSO_MODE", "oidc").lower()


def _bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip() or None
    token_header = os.getenv("ADMIN_UI_SSO_TOKEN_HEADER", "X-SSO-Token")
    return request.headers.get(token_header)


def _claims_roles(claims: dict) -> set[str]:
    roles = set(_roles_from_claims(claims))
    groups = claims.get("groups")
    if isinstance(groups, (list, tuple)):
        roles.update(str(r) for r in groups)
    return roles


def _oidc_user(request: Request) -> Optional[dict[str, Any]]:
    token = _bearer_token(request)
    if not token:
        return None
    if jwt is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OIDC auth not configured",
        )
    secret = os.getenv("ADMIN_UI_OIDC_JWT_SECRET") or get_secret(
        "ADMIN_UI_OIDC_JWT_SECRET_FILE"
    )
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OIDC JWT secret not configured",
        )
    algorithms = [
        alg.strip()
        for alg in os.getenv("ADMIN_UI_OIDC_ALGORITHMS", "RS256").split(",")
        if alg.strip()
    ]
    issuer = os.getenv("ADMIN_UI_OIDC_ISSUER") or None
    audience = os.getenv("ADMIN_UI_OIDC_AUDIENCE") or None
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=algorithms,
            issuer=issuer,
            audience=audience,
            options={"require": ["exp", "iat"]},
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid SSO token"
        ) from exc
    username = (
        claims.get("preferred_username") or claims.get("email") or claims.get("sub")
    )
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="SSO user not found"
        )
    required_role = os.getenv("ADMIN_UI_OIDC_REQUIRED_ROLE")
    required_group = os.getenv("ADMIN_UI_OIDC_REQUIRED_GROUP")
    roles = _claims_roles(claims)
    if required_role and required_role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role"
        )
    if required_group and required_group not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient group"
        )
    return {"username": str(username), "roles": sorted(roles), "provider": "oidc"}


def _saml_user(request: Request) -> Optional[dict[str, Any]]:
    header_user = os.getenv("ADMIN_UI_SAML_HEADER_USER", "X-SSO-User")
    header_groups = os.getenv("ADMIN_UI_SAML_HEADER_GROUPS", "X-SSO-Groups")
    username = request.headers.get(header_user)
    if not username:
        return None
    groups_raw = request.headers.get(header_groups, "")
    groups = {g.strip() for g in groups_raw.split(",") if g.strip()}
    required_group = os.getenv("ADMIN_UI_SAML_REQUIRED_GROUP")
    if required_group and required_group not in groups:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient group"
        )
    return {"username": str(username), "groups": sorted(groups), "provider": "saml"}


def get_sso_user(request: Request) -> Optional[dict[str, Any]]:
    if not _sso_enabled():
        return None
    mode = _sso_mode()
    if mode == "oidc":
        return _oidc_user(request)
    if mode == "saml":
        return _saml_user(request)
    return None
