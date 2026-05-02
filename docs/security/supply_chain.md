# Supply Chain Security

This document outlines the baseline supply-chain controls for AI Scraping
Defense, including dependency integrity, SBOM generation, and CI verification.

## Dependency Integrity

- **Pinned dependencies**: `requirements.lock` is generated from `requirements.txt`
  using `pip-compile` and checked into the repo.
- **Integrity check**: `scripts/security/verify_dependencies.py` validates that
  `requirements.txt` entries are represented in `requirements.lock` and warns
  about insecure index overrides.

## CI Controls

- **Security Controls Workflow**: `.github/workflows/security-controls.yml`
  runs the dependency integrity check as part of the security pipeline.
- **Dependency auditing**: `pip-audit` and related tooling are included in the
  security scan suite.

## SBOM and Image Scanning

- **SBOM**: `syft` generates an SBOM for container images.
- **Image scanning**: `trivy` and `grype` scan images for known CVEs.

## Operational Guidance

- Keep the lockfile updated when dependencies change.
- Prefer HTTPS indexes and avoid `--trusted-host` unless required.
- Review SBOM outputs before production releases.
