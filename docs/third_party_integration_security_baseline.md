# Third-Party Integration Security Baseline

This document defines the current security baseline for supported third-party integrations in the AI Scraping Defense Stack.

## Goals

The baseline exists to keep external integrations:

- explicitly bounded by documented auth, secret, and data-flow rules
- limited to the integration classes the repository actually supports today
- reviewable when new outbound or inbound trust relationships are introduced

## Current Supported Integration Classes

The repository currently supports or documents security-sensitive integrations in these categories:

- alert delivery targets such as Slack webhooks, generic webhooks, and SMTP
- CDN and protected-edge integrations such as Cloudflare
- community blocklist and peer-sync exchanges
- optional cloud dashboard or related operator-facing aggregation services
- GitHub-native security automation for alerts, issues, and response planning

Anything outside those categories should be treated as a new integration class, not silently folded into the current baseline.

## Security Rules

Supported third-party integrations should follow these rules:

- secrets and API tokens come from secret files, environment injection, or Vault-backed paths rather than tracked config
- inbound trust is authenticated and validated before it can mutate state
- outbound callbacks are constrained to documented endpoints and expected auth methods
- integration failures degrade safely and are surfaced through logs, alerts, or audit events
- operator-facing docs explain what data leaves the system and why

## Data-Flow Expectations

Integrations should preserve the existing trust and audit model:

- webhook and alert payloads avoid leaking secrets or unnecessary internal details
- IP, request, and operator data shared externally should be limited to the documented use case
- sync or reputation integrations should remain bounded by explicit policy rather than ad hoc sharing
- changes to external data flow should update the relevant docs in the same pull request

## Required Supporting Documentation

The current baseline is anchored in these docs:

- [configuration.md](configuration.md) for auth and secret settings
- [security/monitoring_and_response.md](security/monitoring_and_response.md) for alerting, audit, and incident handling
- [layered_alerting_architecture.md](layered_alerting_architecture.md) for the alert-delivery model
- [api_trust_boundaries.md](api_trust_boundaries.md) and [inter_service_auth.md](inter_service_auth.md) where trust or auth boundaries apply

## Non-Goals

This baseline does not claim support for arbitrary collaboration suites, document platforms, or file-sharing systems. If the repo adds one of those later, it should come with a specific design and security review instead of being implied by this document.
