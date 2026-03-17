# Release Checklist

Use this checklist before cutting a tagged release.

## Build and Test

- `python3 -m pytest -q test`
- `pip-audit`
- `docker build -t ai-scraping-defense:test .`
- `docker compose config`
- any Rust crates used in production paths pass `cargo test`

## Runtime Validation

- `/health` endpoints respond for the core services in local compose
- Admin UI login works with the configured auth mode
- Redis, PostgreSQL, and NGINX dependencies start cleanly in compose
- suspicious traffic can be blocked, tarpitted, and surfaced in the UI
- `docs/performance_validation.md` evidence is assembled for the release:
  regression-e2e run URL, retained k6 summary, and any staging load notes

## Security and Configuration

- production secrets are injected from the deployment platform, not committed files
- GitHub Actions references are pinned to SHAs
- container release workflow completes with image signing and provenance
- tracked generated artifacts are excluded from the repo tree

## Release Artifacts

- `README.md` matches shipped behavior
- `CHANGELOG.md` reflects the release contents
- `docs/release_artifacts.md` matches the implemented tag policy
- a semver tag `v<major>.<minor>.<patch>` is used for the release
