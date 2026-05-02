## API Versioning Policy

The stack currently publishes a single supported HTTP/WebSocket contract: `unversioned-v1`.

That means:

- existing documented routes remain unversioned
- explicit prefixes such as `/v2/...` or `/api/v2/...` are rejected
- future breaking API generations must introduce an explicit versioned surface instead of silently changing the current paths

## Route Classification

Public routes:

- `GET /list`
- `GET /list/auth`
- `POST /report`
- `POST /webhook`
- `POST /recommendations`
- `POST /api/chat`

Operator routes:

- `GET /`
- `GET /settings`
- `GET /logs`
- `GET /plugins`
- `POST /gdpr/deletion-request`
- `GET /gdpr/compliance-report`
- `GET /metrics`
- `POST /admin/reload_plugins`
- `POST /register`
- `GET /metrics/{installation_id}`
- `GET /defense/*` and other documented management endpoints exposed by the stack

Internal routes:

- `POST /escalate`
- `POST /route`
- `GET /health`
- `GET /ws/{installation_id}`

Internal routes are not a public compatibility promise even when they are HTTP-based. They may evolve behind deployment-controlled service boundaries.

## Deprecation Rules

- `unversioned-v1` is the only supported public/operator contract in the current release line.
- New optional fields may be added to JSON responses without bumping the contract.
- Removing fields, changing semantics, or changing auth requirements requires a new explicit version and migration notes.
- A new explicit version must be documented before release and the previous public/operator version must keep a published deprecation window.
- Unsupported explicit version prefixes return a deterministic `404` JSON response so clients do not silently fall through to unrelated handlers.

## Migration Expectation

When a future `v2` surface is introduced, the repo should:

- keep the existing `unversioned-v1` behavior documented for its deprecation window
- document endpoint-by-endpoint migration notes
- add test coverage for both the supported version and the rejected/deprecated prefixes
