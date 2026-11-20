# Windows Handoff

Use this file to continue the same workstream on your Windows machine.

## 1) Sync the repo on Linux first

If needed, push your latest branch state from Linux:

```bash
git push origin main
```

## 2) Sync on Windows

In PowerShell on your Windows clone:

```powershell
git checkout main
git pull --ff-only origin main
```

## 3) Paste this prompt into a new chat on Windows

```text
Continue work in this repository (Windows clone of ai-scraping-defense).

Current status:
- Cloudflare setup enforcement is implemented.
- Resumable interactive setup is implemented.
- Cloudflare tunnel launchers exist for Linux, macOS, and Windows.

Recent commits:
- 2c6cc3e Add Cloudflare Tunnel launchers for macOS and Windows
- b15c464 Add Cloudflare Tunnel launcher for ISP-blocked hosts
- eb37641 Add resumable setup and Cloudflare config enforcement
- 722e491 Harden tarpit limits and Kubernetes resource ceilings

Next planned step:
1) Validate environment after Cloudflare credentials are set:
   .venv\Scripts\python.exe scripts\validate_env.py
2) If valid, run the stack and tunnel end-to-end on Windows:
   docker compose up -d --build
   .\scripts\windows\start_cloudflare_tunnel.ps1
3) Verify public access and then continue backlog triage.

Important notes:
- Keep functionality intact; do not regress previous CI/CD fixes.
- Prioritize security and runtime stability work.
```

## 4) Windows commands for this exact Cloudflare test flow

```powershell
# Validate env
.venv\Scripts\python.exe scripts\validate_env.py

# Start stack
docker compose up -d --build

# Start quick tunnel
.\scripts\windows\start_cloudflare_tunnel.ps1

# Or named tunnel
$env:CLOUDFLARE_TUNNEL_TOKEN="<your_token>"
.\scripts\windows\start_cloudflare_tunnel.ps1
```
