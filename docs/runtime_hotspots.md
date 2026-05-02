# Runtime Hotspots Audit

This audit captures the request-path hotspots that matter for release readiness and the efficiency patterns expected in the stack.

## Baseline expectations

- Request-path services should use the shared Redis connection helper in `src/shared/redis_client.py` instead of creating ad hoc clients.
- Hot-path outbound HTTP should reuse a process-level client instead of creating a new connection pool per request.
- SQLite-backed lightweight services should enable WAL mode and a bounded busy timeout to reduce lock churn during bursts.

## Changes made in this pass

- `src/iis_gateway/main.py` now uses the shared Redis helper and a reusable `httpx.AsyncClient` for both escalation calls and backend proxying.
- `src/pay_per_crawl/db.py` now enables SQLite `WAL`, `synchronous=NORMAL`, and `busy_timeout=5000` to improve write behavior under concurrent activity.

## Ongoing watch points

- File-backed tarpit and local-training paths still do real disk I/O by design and should stay out of latency-sensitive request paths.
- Operator and maintenance scripts under `scripts/` are not part of the request-path performance baseline and should be judged separately from service runtime behavior.
