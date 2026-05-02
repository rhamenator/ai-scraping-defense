# API Trust Boundaries

This document defines the supported authentication, authorization, and object-scope
baseline for the current release.

## Endpoint Inventory

| Surface | Paths | Authn | Authz / object scope | Notes |
| --- | --- | --- | --- | --- |
| Admin UI | `/`, `/settings`, `/logs`, `/plugins`, `/gdpr/*`, `/metrics`, `/ws/metrics` | HTTP Basic or SSO session, MFA by default | `require_auth` for read surfaces, `require_admin` for state-changing routes | Sessions are Redis-backed; MFA can only be disabled explicitly for lab scenarios. |
| Admin passkey / WebAuthn | `/passkey/*`, `/mfa/*`, `/webauthn/*` | Existing authenticated admin session for registration flows; username-bound challenge/token for login flows | User-bound challenge and token consumption | Tokens and challenges are single-use, username-scoped objects. |
| Escalation engine | `/escalate`, `/admin/reload_plugins` | JWT for protected routes | `escalate:write` / `engine:invoke` or admin roles | Metrics surface is operational, not public API. |
| AI webhook service | `/webhook` | HMAC via `WEBHOOK_SHARED_SECRET` | Action payload validated; IP targets validated before mutation | Rate limited per resolved client IP. |
| Prompt router | `/route` | Bearer shared secret | No object IDs; access is caller-wide | Client IP attribution only trusts configured proxy/CDN CIDRs. |
| Cloud dashboard | `/register`, `/metrics`, `/metrics/{installation_id}`, `/ws/{installation_id}` | `X-API-Key` when `CLOUD_DASHBOARD_API_KEY` is configured; required in production | Metrics and websocket access are installation-scoped | Websocket access also requires prior installation registration. |
| Config recommender | `/recommendations` | `X-API-Key` when `RECOMMENDER_API_KEY` is configured; required in production | Read-only operational output | Production should not expose recommendation output anonymously. |
| Public blocklist | `/list`, `/list/auth`, `/report` | `/report` and `/list/auth` require `X-API-Key`; `/list` is intentionally public | Report path validates IP objects | Public list endpoint is intentionally community-readable. |
| Pay-per-crawl | `/register-crawler`, `/pay`, `/{full_path}` | Crawler token via `X-API-Key` for proxy path | Token-scoped crawler record | Register/pay endpoints are product API surface, not admin endpoints. |
| CAPTCHA services | `/verify`, `/challenge`, `/solve` | Challenge/secret validation, not admin auth | Token-scoped challenge validation | Public by design. |
| Tarpit | `/`, `/health`, `/tarpit/{path}` | None | None | Public deception surface by design. |
| IIS gateway | catch-all ingress route | None at edge; relies on middleware and downstream services | No object IDs | Trusts forwarded identity only through configured proxy/CDN CIDRs. |

## Production Baseline

- `INTERNAL_AUTH_MODE=shared_key` remains the supported internal-service auth mode.
- `SHARED_SECRET`, `PROXY_KEY`, `ESCALATION_API_KEY`, and `WEBHOOK_SHARED_SECRET`
  are required in production.
- `CLOUD_DASHBOARD_API_KEY` is required in production.
- `RECOMMENDER_API_KEY` is required in production.
- Proxy and CDN client IP headers are only trusted when the immediate peer is in
  `SECURITY_TRUSTED_PROXY_CIDRS` or `SECURITY_CDN_TRUSTED_PROXY_CIDRS`.

## Intentional Public Surfaces

The following endpoints remain public by design and should be protected by edge
policy, rate limiting, or product-specific contracts rather than admin auth:

- tarpit routes
- public blocklist `GET /list`
- CAPTCHA challenge / verification flows
- public-facing ingress routes through `iis_gateway`
- pay-per-crawl product routes using crawler tokens rather than operator credentials
