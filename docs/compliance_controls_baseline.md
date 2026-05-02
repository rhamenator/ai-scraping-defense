# Compliance Controls Baseline

This document defines the current compliance-controls baseline for the AI Scraping Defense Stack. It consolidates the repo's practical controls around privacy, retention, auditability, and operator documentation.

## Goals

The baseline exists to ensure the stack has:

- documented privacy and data-handling expectations
- enforceable retention and deletion controls where the repo already implements them
- auditable operational and security evidence for supported workflows
- clear links between code, configuration, and operator-facing compliance documentation

## Current Control Areas

The current compliance baseline is built on the following existing material:

- [legal_compliance.md](legal_compliance.md) for GDPR-oriented product and operator controls
- [privacy_policy.md](privacy_policy.md) for operator-facing data handling disclosures
- [data_protection_baseline.md](data_protection_baseline.md) for storage, transport, backup, and artifact handling
- [security/monitoring_and_response.md](security/monitoring_and_response.md) for audit trails, export, and response workflows

## Minimum Supported Controls

The current repo baseline expects:

- documented legal basis and privacy disclosures for supported personal-data handling
- retention and deletion controls for the data classes the repo stores or exports
- audit logging or equivalent event trails for security-relevant and operator-driven actions
- backup metadata and export controls that preserve evidence for restoration and review
- operator guidance for consent, deletion, and incident-related data handling where those features are enabled

## Configuration Expectations

Deployments that enable the GDPR and privacy features should configure:

- the documented DPO and contact fields
- retention periods appropriate to the operator's jurisdiction and obligations
- consent controls for optional processing paths
- protected audit-log and export destinations

This repo provides the technical hooks, but operators remain responsible for jurisdiction-specific legal advice and final policy decisions.

## Release and Review Expectations

Compliance-relevant changes should ship with:

- matching doc updates when privacy, retention, audit, or disclosure behavior changes
- validation or tests when the code path for deletion, reporting, or audit generation changes
- clear release notes when a change affects operator obligations or expected configuration

## Non-Goals

This baseline does not claim universal regulatory coverage. It defines the practical compliance controls the current repository supports and documents today.
