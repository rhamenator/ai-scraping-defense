# Data Protection Baseline

This document defines the supported production baseline for transport security,
storage handling, backup artifacts, and sensitive-data minimization.

## Transport

- Public ingress should terminate TLS at the stack edge or at a trusted upstream
  proxy/CDN.
- `VAULT_ADDR` must use `https://` in production unless an explicit insecure
  override is set for a lab environment.
- `WEBAUTHN_ORIGIN` must use `https://` in production.
- External classification, webhook, SMTP, and reputation endpoints are expected
  to use HTTPS unless an explicit lab-only insecure override is configured.

## Secrets And Storage

- Runtime secrets should come from secret files or Vault rather than plaintext
  environment variables where possible.
- Security-event exports are written with restrictive file permissions.
- Local Compose-generated secrets remain a local/dev convenience path; production
  deployments should prefer orchestrator-managed secrets or Vault-backed inputs.

## Backups

- `scripts/operations_toolkit.py backup --execute` now writes:
  - `postgres.sql`
  - `redis.rdb`
  - `cluster_state.json`
  - `backup_manifest.json`
- Backup directories are created with restrictive permissions.
- Backup files and metadata are written with restrictive permissions where the
  host OS allows it.
- Restore verifies the checksum manifest before applying backup artifacts.

## Sensitive Data Minimization

- Durable security-event exports redact direct IP fields and secret-like payload
  fields before writing JSONL output.
- Logging formatters mask API keys, passwords, tokens, and IP addresses before
  they reach handler output.
- GDPR/privacy controls remain the baseline for retention, data minimization, and
  deletion workflows.
