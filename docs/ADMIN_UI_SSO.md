# Admin UI SSO (OIDC/SAML)

The Admin UI can authenticate via SSO in addition to HTTP Basic auth. Enable SSO
with environment variables and (optionally) enforce MFA on top of SSO.

## Common settings

- `ADMIN_UI_SSO_ENABLED=true`
- `ADMIN_UI_SSO_MODE=oidc|saml`
- `ADMIN_UI_REQUIRE_MFA=true|false` (default: true)
- `ADMIN_UI_SSO_MFA_REQUIRED=true|false` (defaults to `ADMIN_UI_REQUIRE_MFA`)

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

By default, SSO inherits the release MFA posture from `ADMIN_UI_REQUIRE_MFA`.
If `ADMIN_UI_SSO_MFA_REQUIRED=true`, or `ADMIN_UI_REQUIRE_MFA=true` with no
explicit SSO override, Admin UI 2FA is enforced on top of SSO.

Recommended release posture:

- set `ADMIN_UI_2FA_SECRET` for bootstrap access
- enroll WebAuthn/passkeys for daily operator use
- generate backup codes and store them offline as single-use recovery material

If no 2FA method is configured (TOTP, passkey, or WebAuthn) and MFA is required,
authentication fails. Set `ADMIN_UI_SSO_MFA_REQUIRED=false` only for trusted
lab or integration scenarios where the upstream IdP already guarantees MFA.
