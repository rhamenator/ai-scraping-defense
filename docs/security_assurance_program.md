# Security Assurance Program

This document defines the release-facing security assurance program for the
project. It complements the runtime controls by specifying what external
validation, operator readiness, and third-party review evidence must exist
before a release is considered ready.

## Release Deliverables

Each release candidate should have evidence for all of the following:

1. **Static security baseline**
   - CI security workflows complete successfully.
   - Open alert backlog is triaged through the issue automation path.
   - release notes call out any accepted residual security risk.

2. **Bounded attack regression**
   - the GitHub-hosted attack-regression workflow passes for the current branch
   - results are retained as artifacts for release review
   - failures block the release until triaged or explicitly accepted

3. **Cross-platform external regression**
   - the Regression E2E workflow runs against an explicit staging, preview, or
     production-like URL
   - the target source is documented by workflow input or repository secret
   - failures are triaged as either product regressions or evidence-contract
     problems

4. **External/Kali validation**
   - the self-hosted Kali security sweep runs against an approved staging,
     preview, or release-candidate target
   - findings are attached to the release review, even when the run is
     non-blocking
   - any high-severity findings must be converted into tracked issues before
     release

5. **Operator readiness**
   - monitoring and response runbooks reflect the shipped behavior
   - the release includes operator-facing notes for auth, secrets, backups, and
     incident handling changes
   - at least one operator validates the relevant paths in a staging or lab
     environment

6. **Third-party integration review**
   - newly introduced vendors or hosted services are documented
   - each optional integration has a clear auth/secret model and transport
     expectation
   - security-sensitive vendor dependencies are reviewed before enabling them in
     production guidance

## External Validation Sources

### GitHub-hosted regression

Use `.github/workflows/security-attack-regression.yml` plus
`scripts/security/attack_regression.py` for deterministic PR-time validation.

Expected evidence:

- workflow run URL
- stored JSON artifact
- pass/fail summary for the active profile

### Cross-platform external E2E

Use `.github/workflows/regression-e2e.yml` against an explicit external target.

Expected evidence:

- workflow run URL
- target source (`base_url` input, `STAGING_BASE_URL`, or `PROD_BASE_URL`)
- k6 and pytest artifact/result set for the chosen target

### Self-hosted Kali sweep

Use `.github/workflows/kali-security-sweep.yml` or the operator-run
`scripts/linux/security_scan.sh` flow against approved targets.

Expected evidence:

- target name and approval record
- report bundle location
- triage summary for high/critical findings
- runner identity (self-hosted Kali, WSL, or VM)

## Third-Party Review Expectations

The project supports optional vendors and services such as model providers,
email/webhook endpoints, reputation feeds, CDNs, and Vault.

Before adding or changing a third-party dependency in release guidance:

- document the integration in the relevant setup/configuration doc
- verify transport requirements (`https://`, TLS verification, secret file or
  Vault support)
- describe the blast radius if the provider is compromised or unavailable
- note whether the integration is production-suitable, optional, or lab-only

## Operator Enablement

The minimum operator enablement set for a release is:

- [security/monitoring_and_response.md](security/monitoring_and_response.md)
- [release_checklist.md](release_checklist.md)
- [attack_simulation_profiles.md](attack_simulation_profiles.md)
- any changed setup/deployment doc touched by the release

When a release changes auth, secrets, transport, backups, or incident handling,
the operator notes must be updated in the same change set.

## Closure Criteria

An issue or release gate in this program is considered complete when:

- the required evidence exists in CI artifacts or linked docs
- open findings are either fixed or tracked explicitly with owners
- operators have current runbook material for the shipped behavior

This program is intentionally lightweight: it is meant to make release evidence
explicit, not to replace the runtime security controls already implemented in
the stack.
