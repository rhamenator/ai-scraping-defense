# Admin UI SSO (OIDC/SAML)

The Admin UI can authenticate via SSO in addition to HTTP Basic auth. Enable SSO
with environment variables and (optionally) enforce MFA on top of SSO.

## Common settings

- `ADMIN_UI_SSO_ENABLED=true`
- `ADMIN_UI_SSO_MODE=oidc|saml`
- `ADMIN_UI_SSO_MFA_REQUIRED=true|false` (default: false)

## OIDC mode

Uses a JWT (typically an ID token) provided via `Authorization: Bearer <token>`
or a custom header.

Required:

- `ADMIN_UI_OIDC_JWT_SECRET` (public key or shared secret), or
  `ADMIN_UI_OIDC_JWT_SECRET_FILE`

Optional:

- `ADMIN_UI_OIDC_ALGORITHMS` (default: `RS256`)
- `ADMIN_UI_OIDC_ISSUER`
- `ADMIN_UI_OIDC_AUDIENCE`
- `ADMIN_UI_OIDC_REQUIRED_ROLE`
- `ADMIN_UI_OIDC_REQUIRED_GROUP`
- `ADMIN_UI_SSO_TOKEN_HEADER` (default: `X-SSO-Token`, used when no Bearer token)

## SAML mode

SAML is typically terminated at a reverse proxy or identity provider gateway,
which injects trusted headers. The Admin UI consumes those headers directly.

Required headers:

- `X-SSO-User` (override via `ADMIN_UI_SAML_HEADER_USER`)

Optional:

- `X-SSO-Groups` (override via `ADMIN_UI_SAML_HEADER_GROUPS`)
- `ADMIN_UI_SAML_REQUIRED_GROUP`

## MFA behavior

When `ADMIN_UI_SSO_MFA_REQUIRED=true`, Admin UI 2FA is enforced on top of SSO.
If no 2FA method is configured (TOTP, passkey, or WebAuthn), authentication fails.
