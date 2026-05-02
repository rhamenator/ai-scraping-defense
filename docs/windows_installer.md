# Windows Installer

The Windows installer provides a guided Docker Desktop path:

```powershell
.\scripts\windows\install.ps1
```

By default it:

1. Verifies Docker, Python, `htpasswd`, and the current PowerShell execution
   policy state.
2. Creates `.env` from `sample.env` when needed.
3. Creates local directories and writes local secret files for Docker Compose.
4. Resets the Python virtual environment and installs project dependencies.
5. Validates `.env`.
6. Starts the stack behind the selected Docker-based proxy.
7. Runs the shared installer smoke contract through the Windows wrapper.

## Common Modes

Default Nginx-based install:

```powershell
.\scripts\windows\install.ps1
```

Apache-backed install:

```powershell
.\scripts\windows\install.ps1 -Proxy apache
```

Take over ports `80` and `443`:

```powershell
.\scripts\windows\install.ps1 -Takeover
```

Reuse an existing virtual environment:

```powershell
.\scripts\windows\install.ps1 -SkipVenvReset
```

Regenerate local secrets:

```powershell
.\scripts\windows\install.ps1 -RegenerateSecrets
```

Check optional IIS prerequisites without switching install modes:

```powershell
.\scripts\windows\install.ps1 -CheckIis -SkipSmoke
```

## Shared Smoke Contract

The Windows wrapper delegates to the shared contract in
[installer_contract.md](installer_contract.md):

```powershell
python scripts/installer_smoke_test.py --platform windows --proxy nginx
```

For PowerShell convenience, the wrapper remains:

```powershell
.\scripts\windows\stack_smoke_test.ps1 -Proxy nginx
```

## Uninstall

Stop the stack while keeping data:

```powershell
.\scripts\windows\uninstall.ps1
```

Stop the stack and remove Docker volumes:

```powershell
.\scripts\windows\uninstall.ps1 -PurgeData
```

Attempt to restart IIS/Apache/nginx host services after uninstall:

```powershell
.\scripts\windows\uninstall.ps1 -RestartCommonWebServices
```
