# Internal CAPTCHA Service

The project ships with a lightweight CAPTCHA implementation that can be used instead of Google reCAPTCHA or Turnstile-like service. The service presents a small math challenge and issues a signed token when solved. Challenges are kept on the server: the page carries only a random id, which reveals nothing about the answer, and a challenge can be answered once, whether or not the answer was right. The Escalation Engine verifies this token via the `CAPTCHA_VERIFICATION_URL` setting.

## Endpoints

- `GET /challenge` – renders the challenge page. It loads the fingerprint script from `/__fp.js` so the user's browser fingerprint can be stored in the `fp_id` cookie.
- `POST /solve` – accepts the form submission and returns a JSON payload containing a signed token. Successful attempts are logged.
- `POST /verify` – used by the Escalation Engine. It verifies a token for a given IP address and returns `{"success": true}` or `{"success": false}`.

## Protections and limits

- **One attempt per challenge.** The server stores the answer, the address the challenge was issued to and the browser fingerprint cookie. The first `/solve` for an id consumes it atomically, so a replayed or retried id fails. The answer space is small (2 to 16), so a bot can still win by asking for fresh challenges; the per-client rate limit is what bounds that. Treat this as a speed bump, not proof of humanity.
- **Bound to the client.** A challenge can only be solved from the address that received it (`CAPTCHA_BIND_IP`, default true; turn it off for users whose address changes mid-flow) and, when the browser sent an `fp_id` cookie, with the same fingerprint.
- **Rate limited.** `CAPTCHA_RATE_LIMIT_PER_MINUTE` (default 30, 0 disables) applies separately to `/challenge` and `/solve` per client address, returning 429.
- **Solve time and a client proof (they ask again, they never block).** A correct answer that arrives faster than `CAPTCHA_MIN_SOLVE_SECONDS` (default 1.5; 0 disables) is a bot signal, and so is a missing or wrong `proof`: the page sends a small value computed from the challenge id and your answer (`CAPTCHA_REQUIRE_PROOF`, default true). Either way the attempt fails with `{"success": false, "retry": true}`, no token is issued, nothing is logged as a success, and the page asks for a fresh question. Nothing is blocked or labelled, so a person who is simply fast, or who uses autofill, only has to try again. The proof function is open source, so a bot written for this project can copy it: it filters clients that post the form without running the page, and the minimum time is the check that works whatever the client is. The page adds no hidden field or extra control, so screen readers and password managers are unaffected, and the result message is announced politely.
- **Storage.** Challenges and counters live in Redis when it is reachable, which is required with more than one replica. Otherwise they live in the process's memory (`CAPTCHA_STORE=memory` forces this) and the health check reports `degraded`.
- **`/verify`** accepts the token and address as query parameters (`token`, `ip`) or as the form fields the Escalation Engine sends (`secret`, `response`, `remoteip`); a `secret` that does not match `CAPTCHA_SECRET` is refused. Solved tokens expire after `CAPTCHA_TOKEN_EXPIRY_SECONDS` and may be verified more than once within that time.

## Logging

When a challenge is solved successfully the service appends a JSON line to the file specified by `CAPTCHA_SUCCESS_LOG`:

```json
{"timestamp": "2024-01-01T00:00:00Z", "ip": "1.2.3.4", "fingerprint": "abc123", "ua": "Mozilla/5.0", "result": "success"}
```

Each entry is marked `"source": "captcha_service"`: it is self-reported telemetry from an unauthenticated endpoint. The training pipeline counts these IPs but does **not** relabel traffic as human because of them unless you set `TRAINING_CAPTCHA_OVERRIDES_LABELS=true`.

## Configuration

```
CAPTCHA_SECRET=<random secret>
CAPTCHA_VERIFICATION_URL=http://captcha_service:8004/verify
CAPTCHA_TOKEN_EXPIRY_SECONDS=300
CAPTCHA_BIND_IP=true
CAPTCHA_RATE_LIMIT_PER_MINUTE=30
```

Point `CAPTCHA_VERIFICATION_URL` to your preferred provider. When using this internal service you may also expose the `/challenge` endpoint through your web server so end users can solve the puzzle.
