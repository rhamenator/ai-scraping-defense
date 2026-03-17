# Delivery and Policy Enforcement Security Baseline

This document defines the current delivery-security baseline for the AI Scraping Defense Stack. It captures the minimum expectations for ingress security, release provenance, policy validation, and deployment automation.

## Goals

The delivery baseline should ensure that shipped artifacts and deployment paths are:

- verifiable before promotion
- consistent across preview, staging, and release flows
- guarded by explicit config and policy validation
- compatible with the repo's current ingress and release model

## Ingress and Delivery Boundary

The supported public delivery boundary is still the hardened edge documented in:

- [network_isolation_baseline.md](network_isolation_baseline.md)
- [api_trust_boundaries.md](api_trust_boundaries.md)

Delivery changes must preserve that model:

- public ingress stays on the approved edge
- internal services do not become direct public deployment targets
- operator endpoints remain private or explicitly operator-scoped
- CDN, tunnel, and reverse-proxy integrations preserve trusted client identity rules

## Artifact Integrity Baseline

Release artifacts are governed by [release_artifacts.md](release_artifacts.md). The current baseline requires:

- versioned container publication through GHCR
- pinned third-party images and builder bases
- signed release images
- build provenance attestations
- SBOM attestation from the release workflow

Operators should deploy verified digests rather than mutable tags for production rollouts.

## CI and Policy Validation Baseline

The repository currently enforces delivery and policy expectations through:

- `ci-tests.yml` for core test, lint, config, Helm, and Kubernetes validation
- `security-controls.yml` and related workflows for Trivy, static analysis, and dependency review
- `security-attack-regression.yml` for guarded ingress and abuse regression coverage
- release and preview workflows for image publication and staged deployment paths

Delivery changes should extend those workflows rather than create undocumented side channels.

## Deployment Automation Rules

Deployment automation should follow these rules:

- action references remain pinned
- release, preview, and promotion workflows publish or deploy only from validated artifacts
- environment-specific values stay in tracked configuration rather than ad hoc runner mutations
- canary or staged rollout behavior remains explicit and documented
- new deployment tooling or policy engines must include a compatibility note for the existing supported path

## Policy Enforcement Expectations

The current repo baseline is practical rather than aspirational. Policy enforcement means:

- configuration is validated before deployment or release
- container, Compose, and Kubernetes definitions are scanned and linted
- trust-boundary and exposure regressions are caught by tests or security checks
- provenance and signature verification are documented for operators

This baseline does not require a mandatory service mesh, admission controller, or GitOps platform in every environment. Those remain optional extensions unless and until the repo adopts them as a supported default.

## Required Supporting Evidence

Changes that affect delivery, ingress, or policy enforcement should ship with:

- updated docs for the affected deployment or release path
- matching workflow changes when a gate or artifact contract changes
- validation updates for Compose, Helm, Kubernetes, or security-regression flows as applicable
- rollout and rollback notes when the operator path changes

## Non-Goals

This document does not attempt to define every future admission-control or supply-chain policy feature. It defines the minimum secure delivery baseline the current repo claims to support today.
