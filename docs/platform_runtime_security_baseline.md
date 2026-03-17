# Platform Runtime Security Baseline

This document defines the supported platform-runtime security baseline for the AI Scraping Defense Stack. It consolidates the expectations for container runtime posture, network exposure, secret handling, and operator guidance across the supported deployment paths.

## Goals

The baseline exists to keep deployments:

- explicit about which components are public, operator-only, or internal-only
- aligned across local Compose, CI, and supported production runtimes
- compatible with the repo's hardened container and manifest expectations
- clear about where third-party runtime or platform exceptions still exist

## Supported Runtime Model

The current supported runtime model is:

- containerized services orchestrated by Docker Compose for local and CI workflows
- Kubernetes for production-style clustered deployments
- optional CDN or protected edge-provider deployments in front of the origin
- private service-to-service networking for internal components

The stack does not claim to harden arbitrary hypervisors, VPS images, or vendor-specific control planes beyond the documented container, ingress, and secret-handling assumptions in this repository.

## Exposure Baseline

The network exposure contract is defined in [network_isolation_baseline.md](network_isolation_baseline.md) and enforced in CI. In short:

- only the public edge is intended to receive untrusted internet traffic
- operator surfaces must remain restricted to trusted networks
- development-only published ports are not production exposure approvals
- internal services must stay behind ingress and service discovery

Any deployment that breaks that exposure matrix is outside the supported hardened baseline.

## Container and Manifest Baseline

The hardened runtime expectations are codified in [config/security_hardening.yaml](../config/security_hardening.yaml). Supported first-party runtime paths should:

- run with `no-new-privileges`
- drop Linux capabilities by default
- use `read_only: true` with explicit writable runtime paths where practical
- mount secret material read-only
- keep documented exceptions narrow and justified

Kubernetes workloads should follow the same restricted posture unless a documented exception exists for ingress binding, stateful storage, or packet-capture tooling.

## Trust and Identity Assumptions

Platform-runtime integrations must preserve the repo's existing trust model:

- service-to-service HTTP calls use the documented shared identity contract
- CDN or proxy deployments restore client identity only through trusted proxy ranges
- operator APIs remain authenticated and are not treated as public runtime surfaces
- trust-boundary changes require matching updates to docs and config validation

For the API and service-boundary specifics, see [api_trust_boundaries.md](api_trust_boundaries.md) and [inter_service_auth.md](inter_service_auth.md).

## Secret Handling

Supported runtime integrations must:

- inject secrets from the deployment platform or mounted secret files
- avoid baking live secrets into images, Compose files, or tracked env files
- preserve restrictive file permissions for exported or mounted secret material
- keep backup and export artifacts protected according to [data_protection_baseline.md](data_protection_baseline.md)

## Operator Guidance

Operators are expected to:

- keep public traffic on the approved edge only
- restrict dashboards, metrics, and control surfaces to trusted networks
- use the provided validation and security workflows before exposing a deployment
- treat dev-only services and debug ports as temporary local aids, not production features

## Required Evidence

Changes that affect platform-runtime behavior should ship with:

- updated runtime or deployment docs
- updated validation where the exposure or hardening rules changed
- Compose, Helm, or Kubernetes changes for every supported deployment path affected
- security-regression or release evidence when ingress, trust, or secret behavior changed

## Non-Goals

This baseline does not certify any specific cloud, hypervisor, or third-party runtime product. It defines the security assumptions the stack requires from those environments in order to be considered supported.
