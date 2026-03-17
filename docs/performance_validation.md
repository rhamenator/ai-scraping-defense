# Performance Validation

This document defines the supported performance-validation flow for release
candidates and staging checks. It consolidates the existing scripts and
workflows into one repeatable evidence path.

## Validation Layers

### 1. Runtime metrics and service health

Verify the stack is stable before treating any load test as meaningful:

- `/health`
- `/metrics`
- `/observability/performance/insights`
- `/observability/performance/history`

The stack should be healthy and free of obvious startup degradation before load
tests are interpreted.

### 2. Local and operator load testing

For local experiments or staging smoke tests, use the existing helper tooling
documented in `docs/getting_started.md`:

- `wrk`
- `siege`
- `ab`
- `k6`
- `locust`

These tools are suitable for comparative checks, not for proving production
capacity on their own.

### 3. CI regression validation

The supported CI path is:

- `.github/workflows/regression-e2e.yml`
  - runs `k6` rich flows against the approved base URL
  - runs Python E2E tests
  - runs any repo-local stress/security helper scripts that exist
- `.github/workflows/comprehensive-performance-audit.yml`
  - collects static evidence about caching, pooling, async behavior, profiling,
    and performance-oriented code paths

The regression E2E workflow is the main release-facing performance evidence.
The comprehensive audit is supporting analysis, not a substitute for load
validation.

## Required Release Evidence

For a release candidate, capture:

- workflow run URL for `regression-e2e`
- retained `k6` summary artifact from that run
- any staging or operator-run load-test notes if the release materially changes
  traffic behavior
- a brief note if performance expectations changed or remained stable

## Recommended Review Questions

- Did the request path complete without new 5xx or timeout behavior?
- Did auth, rate limiting, and edge controls still function under load?
- Did the release materially change latency-sensitive code paths?
- Do Grafana/Prometheus metrics show new degradation signals?

## Non-Goals

This workflow does not claim:

- formal capacity certification
- low-level systems benchmarking
- hardware-specific optimization proof

Those concerns remain separate from the release baseline unless profiling data
demonstrates a real bottleneck.
