# Architecture Modernization Baseline

This document defines the current architecture baseline for the AI Scraping Defense Stack. It exists to keep architecture changes practical, reviewable, and compatible with the deployment and security posture the repository already supports.

## Goals

The architecture baseline should preserve:

- a clear request path from ingress to analysis and mitigation
- explicit trust boundaries between public, operator, and internal service traffic
- shared implementation paths for auth, config, persistence, and request identity
- deployable parity across local Compose, CI, and supported production topologies
- room for incremental improvement without forcing a disruptive rewrite

## Current Supported Topology

The current release-oriented topology is:

- `nginx` as the public ingress and first-line request filter
- `ai_service` and `escalation_engine` as the suspicious-request intake and scoring path
- `tarpit_api` as the controlled mitigation endpoint for decoy and slowdown responses
- `admin_ui`, `cloud_proxy`, `prompt_router`, and supporting daemons as operator, model-routing, and background integration services
- `Redis` for hot operational state and `PostgreSQL` for persistent relational content used by supported tarpit and reporting paths

This topology is already documented in [architecture.md](architecture.md), [key_data_flows.md](key_data_flows.md), [inter_service_auth.md](inter_service_auth.md), and [api_versioning.md](api_versioning.md). Architecture work should refine those boundaries, not bypass them.

## Modernization Rules

Architecture changes should follow these rules:

- Prefer extracting shared functionality into `src/shared/` before creating a new service solely to avoid refactoring.
- Treat new internal HTTP calls as contract changes. They must be authenticated, documented, and validated through the shared service-identity path.
- Treat new public or operator-facing endpoints as API-surface changes. They must follow the current versioning and trust-boundary docs.
- Keep local Compose, CI, and deployment manifests aligned. New runtime assumptions should not exist only in one environment.
- Reuse the existing unified Python image strategy unless there is a clear, measurable reason to split build/runtime concerns.
- Keep ingress, rate-limiting, and mitigation decisions near the edge when possible; do not push avoidable hot-path work deeper into Python services.
- Prefer additive, reversible migration steps over all-at-once rewrites.

## Change Triggers

The following classes of change require architecture review and doc updates:

- introducing or removing a service, daemon, or persistent datastore
- changing which component owns a trust decision, block action, tarpit action, or operator control
- adding a new internal network dependency or control-plane integration
- changing the auth contract for service-to-service or operator APIs
- moving functionality between ingress, shared modules, and application services

When those changes happen, update the relevant architecture docs in the same change set.

## Required Supporting Evidence

Architecture changes are not complete unless they also ship:

- updated documentation for topology, trust boundaries, and data flow where applicable
- validation in the relevant CI path (`pytest`, config validation, Compose validation, security regression, or release evidence)
- configuration and deployment updates for the environments the change affects
- compatibility notes when an existing route, env var, or operational workflow changes

## Non-Goals

This baseline does not require adopting a service mesh, event bus, queueing platform, or full clean-architecture rewrite. Those may be worthwhile in the future, but they should not be treated as mandatory modernization by default.

The goal is a coherent, release-worthy system design, not architecture churn.
