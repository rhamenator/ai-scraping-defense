# HTTP Client Retry & Circuit Breaker Policy

The shared async HTTP client (`src/shared/http_client.py`) standardizes retry,
backoff, and circuit breaker behavior across services and alert senders.

## Retry policy

Defaults:

- `HTTP_CLIENT_RETRY_ENABLED=false`
- `HTTP_CLIENT_MAX_RETRIES=2`
- `HTTP_CLIENT_BACKOFF_BASE_SECONDS=0.5`
- `HTTP_CLIENT_BACKOFF_MAX_SECONDS=5.0`
- `HTTP_CLIENT_RETRY_STATUS=429,500,502,503,504`

Behavior:

- Retries apply to network errors/timeouts and the status codes listed in
  `HTTP_CLIENT_RETRY_STATUS`.
- Backoff uses exponential delay with a cap and honors `Retry-After` when present.

## Circuit breaker

Defaults:

- `HTTP_CLIENT_CIRCUIT_ENABLED=false`
- `HTTP_CLIENT_CIRCUIT_FAILURE_THRESHOLD=5`
- `HTTP_CLIENT_CIRCUIT_RESET_SECONDS=30`

Behavior:

- Failures increment per-host counters.
- Once the threshold is reached, the circuit opens for the reset window and
  short-circuits requests to that host.

## Alert sender integration

`src/shared/http_alert.py` uses the shared client and maps `max_retry_attempts`
onto the standardized policy.
