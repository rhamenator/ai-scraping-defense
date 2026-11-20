# AI Scraping Defense: Chat-Relevant Playbook

Last updated: 2026-03-08

This file captures the now-relevant outcomes, decisions, workflows, and operating guidance from this long session history.

## 1. Mission and Product Intent

- Primary goal: ship a secure, reliable, multi-platform anti-scraping defense stack.
- Target users: web server operators (Linux/Apache/Nginx first, plus IIS/Windows, and macOS for development/testing).
- Design intent:
  - Replace or augment managed edge defenses for users who need self-hosted control.
  - Keep setup approachable for non-experts.
  - Preserve functionality while improving security posture and CI/CD stability.

## 2. Environment and Constraints Noted in Session

- Local Linux host used heavily:
  - Ubuntu Server (HP 6300 SFF, 16 GB RAM)
  - Apache bound to port 80 during test takeover phases
  - Docker Desktop can cause memory thrashing on limited hardware
- Additional hosts:
  - Windows machine available (with backup integration)
  - macOS machine available (8 GB RAM noted; lighter runs recommended)
- Important constraint:
  - Residential ISP (Xfinity) blocks inbound hosting ports, so Cloudflare Tunnel is the practical public test path.

## 3. Strategy and Decision Log (High-Level)

- CI/CD and security reliability are release blockers.
- Keep Kubernetes support in code, but treat it as optional for users where risk/cost is not acceptable.
- Prefer real fixes over broad allowlisting for vulnerabilities.
- Separate codifiable issues from non-codifiable/human-factor issues.
- Preserve prior functionality and avoid regressions while resolving conflicts/PR backlog.

## 4. Major Implemented Changes (Recent Core Work)

### 4.1 Runtime Hardening

- Added hard tarpit stream ceiling:
  - `TAR_PIT_MAX_STREAM_SECONDS`
  - Enforced in `src/tarpit/tarpit_api.py` as a hard stop for streamed responses
- Added/expanded Kubernetes resource requests and limits for workloads that lacked them.
- Added regression coverage to enforce security baseline assumptions in tests.

### 4.2 Cloudflare Integration Hardening

- Added stricter env validation for Cloudflare path:
  - If CDN integration is enabled (or strict Cloudflare requirement is enabled), env must include:
    - provider check (`cloudflare`)
    - token/token-file
    - zone ID (or explicit purge URL)
- Improved CDN purge URL construction from `CLOUD_CDN_ZONE_ID`.
- Strengthened interactive setup behavior:
  - prompts for Cloudflare-required values when feature enabled
  - setup pause/resume support via `.interactive_setup_state.json`

### 4.3 Cloudflare Tunnel Support for ISP-Blocked Hosts

- Added one-command tunnel launch scripts:
  - Linux: `scripts/linux/start_cloudflare_tunnel.sh`
  - macOS: `scripts/macos/start_cloudflare_tunnel.zsh`
  - Windows: `scripts/windows/start_cloudflare_tunnel.ps1`
- Added docs and env template updates for tunnel token/target URL usage.

## 5. Key Commits to Know

- `722e491` - Harden tarpit limits and Kubernetes resource ceilings
- `eb37641` - Add resumable setup and Cloudflare config enforcement
- `b15c464` - Add Cloudflare Tunnel launcher for ISP-blocked hosts (Linux)
- `2c6cc3e` - Add Cloudflare Tunnel launchers for macOS and Windows

## 6. Cloudflare Credentials Needed for This Stack

Two separate credentials may be needed:

1. Cloudflare API Token (for cache purge integration in app code)
2. Cloudflare Tunnel Token (for `cloudflared` public ingress without opening inbound ISP-blocked ports)

### 6.1 API Token (cache purge)

- Minimal permission for the current integration:
  - `Zone -> Cache Purge -> Purge`
- Resource scope:
  - specific zone for your domain
- Also capture zone ID for env settings.

### 6.2 Tunnel Token (public access)

- From Cloudflare Zero Trust tunnel creation flow.
- Used by the tunnel launcher scripts in named mode.

## 7. Required/Important Environment Variables

Core Cloudflare/CDN:

- `ENABLE_GLOBAL_CDN=true`
- `CLOUD_CDN_PROVIDER=cloudflare`
- `CLOUD_CDN_ZONE_ID=<zone_id>`
- `CLOUD_CDN_API_TOKEN=<token>` or `CLOUD_CDN_API_TOKEN_FILE=<path>`
- `REQUIRE_CLOUDFLARE_ACCOUNT=true` (strict mode)

Cloudflare Tunnel:

- `CLOUDFLARE_TUNNEL_TOKEN=<tunnel_token>` (for named tunnels)
- `CLOUDFLARE_TUNNEL_TARGET_URL=http://localhost:<port>` (optional override)

## 8. Validation and Test Flow (Recommended Order)

After setting `.env`:

1. Validate env:

```bash
.venv/bin/python scripts/validate_env.py
```

2. Start stack:

```bash
docker compose up -d --build
```

3. Start Cloudflare tunnel:

- Linux:

```bash
./scripts/linux/start_cloudflare_tunnel.sh
```

- macOS:

```bash
./scripts/macos/start_cloudflare_tunnel.zsh
```

- Windows:

```powershell
.\scripts\windows\start_cloudflare_tunnel.ps1
```

4. Verify public access from external client/network.
5. Run security smoke/security scan as appropriate.

## 9. Security Testing Philosophy Captured in Session

- Security scan scripts should emulate realistic attacker behavior.
- Avoid superficial pass/fail allowlisting unless risk is understood and contained.
- If a finding is non-codifiable (organizational/culture-only), track as process/roadmap item, not code defect.
- Keep secrets out of repo and avoid embedding live credentials in scripts/history.

## 10. CI/CD and Quality Guidance Captured

- Run pre-commit on changed files.
- Run pytest when Python code/tests change.
- Keep workflow fixes incremental and reversible.
- Prefer pinned actions and robust workflow guards.
- Add `workflow_dispatch` for operational workflows where manual control is useful.

## 11. Issue and PR Triage Heuristics Used

- Prioritize by criticality first:
  - security vulnerabilities
  - runtime regressions
  - CI blockers
  - performance regressions
  - remaining backlog
- Resolve easy safe merges first only if they do not regress prior core fixes.
- For stale/vague WIP/closed items:
  - close or relabel if non-codifiable/moot
  - split large risky scopes into smaller tested changes
  - preserve original intent where safe

## 12. Operational Reality: What Is Still External/Manual

Code now covers many safeguards, but these remain operator responsibilities:

- Cloud billing alerts / budget alarms
- Cluster autoscaler upper bounds (provider side)
- Provider abuse handling and response runbook
- DNS and Cloudflare account/tunnel setup details

## 13. Cross-Machine Handoff Pattern

- Keep this file plus `WINDOWS_HANDOFF.md` for context transfer.
- Push branch state before switching machines.
- Pull fast-forward only on target machine.
- Re-run env validation on each machine before stack launch.

## 14. Known Good Commands Cheat Sheet

### Repo health

```bash
git status -sb
git log --oneline -n 10
```

### Quality gates

```bash
.venv/bin/pre-commit run --files <changed files...>
.venv/bin/python -m pytest
```

### Cloudflare stack checks

```bash
.venv/bin/python scripts/validate_env.py
docker compose up -d --build
./scripts/linux/start_cloudflare_tunnel.sh
```

### Windows equivalents

```powershell
.venv\Scripts\python.exe scripts\validate_env.py
docker compose up -d --build
.\scripts\windows\start_cloudflare_tunnel.ps1
```

## 15. Current Suggested Next Steps

1. Finish Cloudflare credential setup in `.env`.
2. Run env validation (step 3) with full agency permissions.
3. Launch stack + tunnel and verify external reachability.
4. Run targeted smoke + security checks.
5. Continue backlog triage from highest criticality items.

## 16. Safety Note

- Do not commit real credentials, API tokens, or private keys.
- Use secret files and/or secret managers where possible.
