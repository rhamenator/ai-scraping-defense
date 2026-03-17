# Inter-Service Authentication

The current supported production baseline for internal HTTP calls is
`INTERNAL_AUTH_MODE=shared_key`.

This release does not claim mTLS or workload-identity support. Instead, it makes
the existing shared-secret contract explicit, validates it in production, and
tests the protected call paths that already exist in the stack.

## Internal HTTP Auth Matrix

| Caller | Callee | Endpoint / hop | Auth contract |
| --- | --- | --- | --- |
| External caller or trusted edge service | `prompt_router` | `POST /route` | `Authorization: Bearer $SHARED_SECRET` |
| `prompt_router` | `cloud_proxy` | `POST /api/chat` | `X-Proxy-Key: $PROXY_KEY` |
| `admin_ui` | `escalation_engine` | `/admin/reload_plugins` and other admin calls | `X-API-Key: $ESCALATION_API_KEY` |
| `escalation_engine` | `ai_service` | `/webhook` | `X-Signature` HMAC using `$WEBHOOK_SHARED_SECRET` |

## Production Validation

When `APP_ENV=production` and `INTERNAL_AUTH_MODE=shared_key`, the configuration
validator requires:

- `SHARED_SECRET`
- `PROXY_KEY`
- `ESCALATION_API_KEY`
- `WEBHOOK_SHARED_SECRET`

This keeps the stack from bootstrapping a production deployment with missing
internal auth secrets.

## Next Step

If the project later adds mTLS or workload identity, it should be introduced as
an additional explicit `INTERNAL_AUTH_MODE` with its own config validation and
endpoint tests, rather than as an implicit side path.
