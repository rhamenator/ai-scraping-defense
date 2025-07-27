# Internal CAPTCHA Service

The project ships with a lightweight CAPTCHA implementation that can be used instead of Google reCAPTCHA or Turnstile-like service. The service presents a small math challenge and issues a signed token when solved. The Escalation Engine verifies this token via the `CAPTCHA_VERIFICATION_URL` setting.

## Endpoints

- `GET /challenge` – renders the challenge page. It loads the fingerprint script from `/__fp.js` so the user's browser fingerprint can be stored in the `fp_id` cookie.
- `POST /solve` – accepts the form submission and returns a JSON payload containing a signed token. Successful attempts are logged.
- `POST /verify` – used by the Escalation Engine. It verifies a token for a given IP address and returns `{"success": true}` or `{"success": false}`.

## Logging

When a challenge is solved successfully the service appends a JSON line to the file specified by `CAPTCHA_SUCCESS_LOG`:

```json
{"timestamp": "2024-01-01T00:00:00Z", "ip": "1.2.3.4", "fingerprint": "abc123", "ua": "Mozilla/5.0", "result": "success"}
```

This makes it easy to feed CAPTCHA results into the training pipeline. Fingerprint and user agent information allow more advanced analysis.

## Configuration

```
CAPTCHA_SECRET=<random secret>
CAPTCHA_VERIFICATION_URL=http://captcha_service:8004/verify
CAPTCHA_TOKEN_EXPIRY_SECONDS=300
```

Point `CAPTCHA_VERIFICATION_URL` to your preferred provider. When using this internal service you may also expose the `/challenge` endpoint through your web server so end users can solve the puzzle.
