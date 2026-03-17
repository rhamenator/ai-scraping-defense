# Reliability and Capacity Operations Baseline

This document defines the current operations baseline for reliability, resilience, and capacity management in the AI Scraping Defense Stack.

## Goals

The baseline exists to make the platform:

- predictable under normal and degraded load
- measurable through explicit health, metrics, and operator workflows
- recoverable through documented backup, restore, and incident paths
- clear about what release-ready operational evidence looks like

## Reliability Baseline

The stack should maintain:

- working `/health` endpoints for core services
- observable request, latency, and error signals through the monitoring stack
- documented incident handling and mitigation steps in [operations_playbooks.md](operations_playbooks.md)
- backup and restore paths in [disaster_recovery.md](disaster_recovery.md)

Operational changes should preserve those paths rather than introduce undocumented service-specific recovery behavior.

## Capacity Baseline

Capacity management currently depends on:

- Prometheus and Grafana visibility into service latency, request rates, and resource usage
- request-path hotspot awareness from [runtime_hotspots.md](runtime_hotspots.md)
- Redis, PostgreSQL, ingress, and worker behavior staying within documented operator expectations
- regular review of queue depth, CPU, memory, and request latency trends

This repository does not yet claim fully automated capacity planning. The supported baseline is documented metrics, reviewable signals, and explicit operator action when thresholds are exceeded.

## Required Operational Evidence

Release and high-risk infrastructure changes should have evidence for:

- successful test and config validation in CI
- healthy local or staging startup for the affected services
- known rollback or restore steps if the change affects data, routing, or operator workflows
- updated dashboards, alerts, or operator notes when new failure modes are introduced

## Incident and Recovery Expectations

When reliability behavior changes, update the matching operational material:

- [operations_playbooks.md](operations_playbooks.md) for detection, mitigation, and communication
- [disaster_recovery.md](disaster_recovery.md) for backup, restore, and drill expectations
- [monitoring_stack.md](monitoring_stack.md) for metrics, dashboards, and observability signals

## Non-Goals

This baseline does not require digital twin simulation, mandatory chaos tooling, or fully autonomous remediation. Those are future maturity options, not current release gates.
