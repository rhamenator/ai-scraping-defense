# Linux Installer

The Linux installer promotes the existing setup, proxy, and smoke-test scripts
into one guided entrypoint:

```bash
sudo ./scripts/linux/install.sh
```

By default it:

1. Verifies Docker, Compose, Python 3.10+, `htpasswd`, `curl`, and other
   required host tools.
2. Creates `.env` from `sample.env` if needed.
3. Creates local directories and local development secrets.
4. Resets the Python virtual environment and installs project dependencies.
5. Validates `.env`.
6. Starts the stack behind the recommended containerized Nginx proxy.
7. Runs `scripts/linux/stack_smoke_test.sh` to confirm the install.

## Common Modes

Local coexistence with host Apache or nginx:

```bash
sudo ./scripts/linux/install.sh
```

Apache-backed install instead of Nginx:

```bash
sudo ./scripts/linux/install.sh --proxy apache
```

Take over ports `80` and `443` after snapshotting host web-server config:

```bash
sudo ./scripts/linux/install.sh --takeover
```

Reuse an existing virtual environment:

```bash
./scripts/linux/install.sh --skip-venv-reset
```

Regenerate local secrets:

```bash
./scripts/linux/install.sh --regenerate-secrets
```

## Smoke Contract

The installer calls the shared contract defined in
[installer_contract.md](installer_contract.md):

```bash
python scripts/installer_smoke_test.py --platform linux --proxy nginx
```

For shell compatibility, the Linux wrapper remains:

```bash
scripts/linux/stack_smoke_test.sh --proxy nginx
```

Success output is line-oriented and intended to be human-readable:

```text
=== Stack Smoke Test (Linux / nginx) ===
[OK] postgres_markov_db is running (health=healthy)
[OK] redis_store is running (health=healthy)
...
Smoke test passed.
```

Any failed assertion prints a `[FAIL]` line and exits non-zero.

## Rollback and Uninstall

Stop the stack while keeping data volumes:

```bash
./scripts/linux/uninstall.sh
```

Stop the stack and remove Docker volumes:

```bash
./scripts/linux/uninstall.sh --purge-data
```

Restore the most recent Apache/nginx host snapshot after a takeover install:

```bash
./scripts/linux/uninstall.sh --restore-webserver latest
```

Restore a specific snapshot:

```bash
./scripts/linux/uninstall.sh --restore-webserver backups/webserver/<timestamp>
```

If you used `--takeover`, the pre-takeover snapshot lives under
`backups/webserver/`.
