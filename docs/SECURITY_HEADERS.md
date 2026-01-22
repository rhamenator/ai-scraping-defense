# Security Header Policy

This project enforces a standard set of response headers across services via the
shared middleware in `src/shared/middleware.py`. These defaults are applied to
every response unless a handler sets a header explicitly.

## Default policy

- `X-Frame-Options`: `DENY`
- `X-Content-Type-Options`: `nosniff`
- `Referrer-Policy`: `no-referrer`
- `Permissions-Policy`: `geolocation=(), microphone=(), camera=()`
- `X-Permitted-Cross-Domain-Policies`: `none`
- `X-XSS-Protection`: `1; mode=block`
- `Content-Security-Policy`: `default-src 'self'`
- `Strict-Transport-Security`: `max-age=31536000; includeSubDomains; preload`
  (only when `ENABLE_HTTPS=true`)

## Overrides for edge cases

1. Per-response overrides
   - Set the header directly in a route/response.
   - The security middleware uses `setdefault`, so explicitly-set values win.

2. Environment overrides (global defaults)
   - `SECURITY_HEADER_X_FRAME_OPTIONS`
   - `SECURITY_HEADER_X_CONTENT_TYPE_OPTIONS`
   - `SECURITY_HEADER_REFERRER_POLICY`
   - `SECURITY_HEADER_PERMISSIONS_POLICY`
   - `SECURITY_HEADER_X_PERMITTED_CROSS_DOMAIN_POLICIES`
   - `SECURITY_HEADER_X_XSS_PROTECTION`
   - `SECURITY_HEADER_CSP`
   - `SECURITY_HEADER_HSTS` (effective only when `ENABLE_HTTPS=true`)

3. Admin UI CSP override
   - `ADMIN_UI_CSP` can override the CSP for Admin UI responses.
