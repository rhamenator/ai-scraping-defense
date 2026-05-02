# CI / Security / Regression — v9

**Pipelines**
- CI Tests (Linux/Windows/macOS): unit tests + linters; NGINX syntax; Helm/Kubeconform validation.
- Security Audit: CodeQL, Semgrep, Trivy (fs+config), Bandit, pip-audit, npm/yarn audit, gosec/govulncheck, cargo-audit, hadolint, shellcheck, luacheck, md/yaml lint → roll-up to `reports/summary.json`.
- Security Autofix: creates a PR with safe formatting/lint fixes (ruff/black/isort, eslint/prettier, luacheck/stylua, shfmt, hadolint, kubeconform).
- Security Attack Regression: required GitHub-hosted Linux security gate. PR and `main` runs use a self-contained local Compose stack; manual runs can also target an approved external staging URL with the bounded `staging-v1` profile.
- Kali Security Sweep: self-hosted Linux/Kali workflow for broader tool-heavy validation against approved staging, preview, or release-candidate targets.
- Regression E2E: k6 + pytest across OSes against an explicit external target; also runs your `security_test.*` and `stress_test.*` scripts if present.
- Windows IIS (self-hosted): ARR/URL Rewrite install + smoke + k6.
- Deploy Staging: builds only contexts that have `Dockerfile` (repo root, `proxy/`, `prompt-router/`, `cloud-proxy/`) and deploys with Helm.
- Deploy Production: manual or `v*` tags; environment-gated.
- Promote on Green: auto prod deploy when staging E2E passes (still requires production env approval).
- PR Previews: per-PR namespaces & URLs, auto cleanup.
- Canary Shift: adjust NGINX canary weight (0–100).

## Runner Topology

- Use GitHub-hosted `ubuntu-latest` for deterministic required security regression gates.
- Use a self-hosted runner labeled `linux`, `kali`, and `security-scan` for broader sweeps that need heavier offensive tooling.
- WSL-based Kali is acceptable for manual or ad hoc operator-driven scans.
- A dedicated Kali VM is preferred for scheduled self-hosted sweeps because it is easier to keep stable as a long-lived runner.
