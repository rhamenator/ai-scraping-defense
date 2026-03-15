# Installer Smoke and Uninstall Contract

This repository now defines one shared post-install validation path:

```bash
python scripts/installer_smoke_test.py --platform <linux|windows|macos> --proxy <nginx|apache>
```

Platform wrappers may still exist for operator convenience, but they should
delegate to this shared contract where possible instead of re-implementing the
health checks independently.

## Required Success Output

Installers should surface smoke-test results as line-oriented text:

```text
=== Stack Smoke Test (linux / nginx) ===
[OK] postgres_markov_db is running (health=healthy)
[OK] redis_store is running (health=healthy)
...
Smoke test passed.
```

Failures should emit exactly one `[FAIL]` line describing the first unmet
contract and exit non-zero.

## Current Coverage

- `linux`: implemented via `scripts/linux/stack_smoke_test.sh`, which delegates
  to `scripts/installer_smoke_test.py`
- `windows`: implemented via `scripts/windows/stack_smoke_test.ps1`, which delegates
  to `scripts/installer_smoke_test.py`
- `macos`: pending installer wrapper

## Required Checks

The shared smoke path validates:

- core containers are running and healthy:
  - `postgres_markov_db`
  - `redis_store`
  - `admin_ui`
  - `escalation_engine`
  - `tarpit_api`
- selected proxy container is running and healthy:
  - `nginx_proxy` or `apache_proxy`
- selected proxy serves HTTP on the mapped host port
- `nginx_proxy` also serves HTTPS on the mapped host port
- `admin_ui` health endpoint is reachable
- `tarpit_api` health endpoint is reachable
- `escalation_engine` health payload reports `healthy` or `degraded`

## Uninstall and Rollback Guidance

Every platform installer should document:

1. how to stop the stack while preserving data
2. how to remove persistent volumes or local caches
3. how to restore any host web-server state if takeover mode was used

Current Linux commands:

```bash
./scripts/linux/uninstall.sh
./scripts/linux/uninstall.sh --purge-data
./scripts/linux/uninstall.sh --restore-webserver latest
```
