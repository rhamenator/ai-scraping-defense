# Runtime Performance Baseline

This document defines the current runtime performance baseline for the stack.
It is not a promise of universal capacity; it is the supported operator-facing
reference for what to watch, what to review, and how to interpret the current
service-level guidance.

## Core Service Expectations

The current baseline inherits the SLO-oriented expectations already used in
operations:

| Service | Baseline expectation | Primary evidence |
| --- | --- | --- |
| Escalation Engine | 99.9% of requests under 1.5s | request latency metrics, health checks |
| AI Service | 99.5% webhook latency under 500ms | latency histograms, audit flow stability |
| Admin UI | 99% availability | `/health`, auth flow health |
| Tarpit API | error rate under 0.5% | request/error counters |
| Cloud Dashboard | metrics fanout under 2s | request latency and websocket behavior |

These are operational review targets, not customer-facing contractual SLAs.

## Capacity Review Signals

The minimum signals to review are:

- CPU usage by service
- memory usage by service
- request latency percentiles (`p50`, `p95`, `p99`)
- queue/concurrency depth where exposed
- Redis and PostgreSQL health under load
- performance insights and degradation events from the shared observability layer

If utilisation stays above 70% of allocated resources for multiple review
windows, operators should plan scaling or workload redistribution.

## Deployment Tiers

### Development / evaluation

- 4 CPU cores
- 8 GB RAM
- 10 GB free storage

### Small deployment

- 8 CPU cores
- 16 GB RAM
- 20 GB free storage

### Larger deployment

- 16+ CPU cores
- 32+ GB RAM
- 40+ GB free storage

Optional local LLM containers materially change these requirements and should be
treated as separate capacity tiers.

## Scaling Guidance

- scale stateless services horizontally before chasing speculative low-level
  optimizations
- use Prometheus/Grafana metrics and the performance analytics endpoints to
  justify scaling decisions
- cluster or externalize Redis/PostgreSQL when reliability or sustained load
  demands it
- use HPAs or equivalent autoscaling only after the target metrics and review
  thresholds are understood

## Review Cadence

- during release validation: confirm the regression/load evidence from
  `docs/performance_validation.md`
- weekly: review capacity dashboards and recent degradation signals
- after incidents or major traffic changes: compare current metrics against the
  most recent stable release evidence

## Non-Goals

This baseline does not claim:

- CPU micro-optimization
- hardware-specific tuning
- low-level kernel or memory subsystem tuning
- guaranteed results across all infrastructure providers

Those remain separate research or hotspot-audit work items unless profiling data
proves they are necessary.
