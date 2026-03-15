# macOS Installer

The macOS installer provides a guided Docker Desktop path:

```bash
./scripts/macos/install.zsh
```

By default it:

1. Verifies Docker Desktop, Python 3.10+, `htpasswd`, `curl`, and other host tools.
2. Creates `.env` from `sample.env` when needed.
3. Creates local directories and writes local secret files for Docker Compose.
4. Resets the Python virtual environment and installs project dependencies.
5. Validates `.env`.
6. Starts the stack behind the selected Docker-based proxy.
7. Runs the shared installer smoke contract through the macOS wrapper.

## Common Modes

Default Nginx-based install:

```bash
./scripts/macos/install.zsh
```

Apache-backed install:

```bash
./scripts/macos/install.zsh --proxy apache
```

Take over ports `80` and `443`:

```bash
./scripts/macos/install.zsh --takeover
```

Reuse an existing virtual environment:

```bash
./scripts/macos/install.zsh --skip-venv-reset
```

Regenerate local secrets:

```bash
./scripts/macos/install.zsh --regenerate-secrets
```

## Shared Smoke Contract

The macOS wrapper delegates to the shared contract in
[installer_contract.md](installer_contract.md):

```bash
python scripts/installer_smoke_test.py --platform macos --proxy nginx
```

For shell convenience, the wrapper remains:

```bash
./scripts/macos/stack_smoke_test.zsh --proxy nginx
```

## Uninstall

Stop the stack while keeping data:

```bash
./scripts/macos/uninstall.zsh
```

Stop the stack and remove Docker volumes:

```bash
./scripts/macos/uninstall.zsh --purge-data
```
