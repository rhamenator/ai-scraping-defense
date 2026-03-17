# Guarded Attack Simulation Profiles

`scripts/security/attack_regression.py` provides bounded attack-simulation
profiles for validating the defensive stack without turning the repo into a
general-purpose offensive scanner.

## Safety Controls

- Every target host must be explicitly allowlisted with `--allow-host`.
- Each profile enforces a maximum outbound request budget.
- Profiles are versioned so CI, staging, and Kali runs can stay reproducible.
- Output is machine-readable JSON suitable for CI artifacts and nightly reviews.

## Profiles

- `compose-v1`
  - local Compose regression profile
  - covers HTTPS redirect, security headers, auth rejection, websocket rejection,
    size limits, and prompt-router rate limiting
- `staging-v1`
  - bounded external profile for approved staging targets
  - adds a selected WAF payload probe on top of the core edge/admin checks
- `kali-v1`
  - same guardrails as staging, intended for self-hosted Kali runners or
    operator-driven sweeps against approved preview infrastructure

## Example Commands

Local Compose:

```bash
python scripts/security/attack_regression.py \
  --profile compose-v1 \
  --nginx-http-base http://127.0.0.1:8088 \
  --nginx-https-base https://127.0.0.1:8443 \
  --admin-ui-base http://127.0.0.1:5002 \
  --prompt-router-base http://127.0.0.1:8009 \
  --prompt-shared-secret "$SHARED_SECRET" \
  --allow-host 127.0.0.1 \
  --output-path reports/attack-regression.json \
  --json
```

Approved staging target:

```bash
python scripts/security/attack_regression.py \
  --profile staging-v1 \
  --nginx-http-base http://staging.example.test \
  --nginx-https-base https://staging.example.test \
  --admin-ui-base https://admin.example.test \
  --allow-host staging.example.test \
  --allow-host admin.example.test \
  --output-path reports/staging-attack-regression.json \
  --json
```

Self-hosted Kali runner:

```bash
python scripts/security/attack_regression.py \
  --profile kali-v1 \
  --nginx-http-base http://preview.example.test \
  --nginx-https-base https://preview.example.test \
  --admin-ui-base https://admin.preview.example.test \
  --allow-host preview.example.test \
  --allow-host admin.preview.example.test \
  --output-path reports/kali-attack-regression.json \
  --json
```

## Guardrail Notes

- Treat `--allow-host` as a positive authorization list, not a convenience flag.
- Increase `--max-requests` only when a specific profile requires it.
- Keep this tool focused on defensive validation. Broader recon and
  opportunistic scanning remain in the separate Kali security sweep workflow.
- Use GitHub-hosted Linux runners for `compose-v1` and bounded `staging-v1`
  validation. Use the self-hosted Kali sweep for broader tool-driven scanning.
