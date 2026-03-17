# Engineering Quality Baseline

This document defines the current engineering-quality baseline for the AI Scraping Defense Stack. It is intended to turn broad "code quality" goals into concrete expectations that contributors, reviewers, and release owners can verify.

## Goals

The baseline exists to keep the stack:

- maintainable across multiple Python services and support scripts
- testable on Linux, Windows, and macOS
- predictable under CI and release workflows
- safe to evolve without weakening security, observability, or deployment behavior

## Contributor Expectations

Before opening a pull request, contributors should:

- run `pre-commit` on changed files
- run the relevant test suite for the area they changed
- keep changes small enough for focused review when possible
- update docs when behavior, configuration, or deployment expectations change
- avoid mixing unrelated refactors with behavioral fixes

For broad setup instructions, see [../CONTRIBUTING.md](../CONTRIBUTING.md). For scanning-specific workflows, see [code_scanning_process.md](code_scanning_process.md).

## Required Validation

The minimum local validation depends on the change:

- Python code or tests: `python -m pytest -q test`
- shell scripts: `pre-commit` and syntax validation where applicable
- PowerShell scripts: `pre-commit` and script-analyzer compatibility
- Docker, NGINX, or deployment config: `docker compose config` and the relevant config validation path
- release-facing performance or security changes: update the supporting evidence called out in the release and assurance docs

Contributors should prefer the narrowest useful command while iterating, then run the broader suite before merge if the change can affect shared behavior.

## CI Baseline

The repository's baseline quality gate is the `CI Tests (Linux, Windows, macOS)` workflow in `.github/workflows/ci-tests.yml`. It currently enforces:

- Python test execution on Linux, Windows, and macOS
- Rust test, formatting, and clippy coverage for tracked crates
- Node test execution when frontend packages are present
- shell linting with ShellCheck
- Lua linting with `luacheck`
- NGINX syntax validation using the hardened OpenResty configuration
- Helm and Kubernetes manifest validation where chart content exists

Additional targeted workflows cover release images, attack-regression checks, code scanning, and security automation. Those workflows complement the baseline; they do not replace it.

## Engineering Rules

Changes should preserve or improve the following properties:

- Inputs are validated before they influence routing, shell execution, persistence, or outbound requests.
- Outputs are encoded or constrained appropriately for HTML, JSON, shell, and config contexts.
- Exceptions fail safely, emit useful logs, and do not leak secrets or internal-only details.
- Shared utilities are reused instead of reimplementing auth, secret loading, request identity, or Redis access ad hoc in each service.
- Long-lived resources such as HTTP clients, database handles, and Redis connections are reused or cleaned up explicitly.
- New dependencies are justified, pinned through the repo's dependency management flow, and covered by the existing audit path.
- Tests cover both the intended success path and at least the key failure or abuse path for the change.

## Review Expectations

Reviewers should look for:

- behavioral regressions in request handling, auth, persistence, and operator workflows
- missing tests or docs for new config, deployment, or API behavior
- duplicate logic that should move into shared modules
- weak error handling, silent failure, or misleading logging
- hidden runtime costs such as per-request client creation, blocking I/O on hot paths, or repeated config parsing

## Release Evidence

Release candidates should have objective evidence that the baseline still holds:

- CI is green on the release commit
- release checklist items in [release_checklist.md](release_checklist.md) are complete
- performance evidence in [performance_validation.md](performance_validation.md) is current when request-path behavior changed
- security evidence in [security_assurance_program.md](security_assurance_program.md) is current when trust boundaries, auth, or attack handling changed

## Out of Scope

This baseline is intentionally practical. It does not attempt to encode speculative research work, experimental architecture ideas, or culture goals. Those belong in roadmap issues and design work, not in the required merge gate for everyday changes.
