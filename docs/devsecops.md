# DevSecOps Integration

This document describes how security controls are integrated into CI/CD for the
AI Scraping Defense project and how to extend them safely.

## Current Security Workflows

The repository already runs multiple security-focused workflows:

- `security-controls.yml` runs static analysis, targeted security tests, and
  dependency audits.
- `pip-audit.yml` runs dependency vulnerability checks and can regenerate the
  lockfile.
- `container-image-scan.yml` performs scheduled container image scans.
- `codacy.yml`, `devskim.yml`, and CodeQL jobs report additional findings.

## Extending the Pipeline

When adding new security tooling:

1. Prefer scheduled or manually triggered workflows for heavier scans.
2. Use SARIF uploads so findings appear in the GitHub security tab.
3. Avoid blocking deploy workflows unless the scan is a gating requirement.
4. Pin action versions and CLI installers to known-good releases.

## Release Safety Checklist

- All security workflows pass or are intentionally skipped with a documented
  reason.
- Dependency updates are tracked in `requirements.lock`.
- Secrets are sourced from the configured secrets provider (Vault, k8s secrets,
  or Docker secrets).

## Next Steps

- Add more targeted tests when new controls are introduced.
- Expand artifact retention for compliance needs.
