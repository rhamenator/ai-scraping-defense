# Performance Innovation Roadmap

This document captures performance research initiatives that are intentionally
outside the current release baseline. These items stay here until real profiling
data shows they are worth productizing.

## Focus Areas

- Adaptive rate limiting and dynamic thresholds
- Improved anomaly detection pipelines
- Data-driven optimization of tarpit generation
- Resource efficiency in containerized environments

## Low-Level Research Track

The following topics are explicitly tracked as experimental low-level research,
not release blockers:

- memory hierarchy and allocation tuning
- hardware acceleration or GPU offload
- serialization and compression strategy changes
- memory-mapped file experiments
- predictive caching ideas
- kernel-bypass or real-time tuning
- storage-path optimizations such as SSD-specific tuning

These ideas should not bypass the normal profiling-first rule. If a proposal
does not correspond to a measured bottleneck in the current Python and
microservice stack, it stays in this roadmap instead of turning into mandatory
release work.

## Evaluation Criteria

- Measurable latency or throughput improvement
- No regression in detection accuracy
- Clear rollback strategy
- Observability coverage for new behavior

## Next Steps

- Identify top bottlenecks in production traces.
- Prototype in isolated, feature-flagged modules.
- Add benchmark tests before rollout.
- Promote ideas out of this roadmap only when profiling and operator evidence
  justify the extra complexity.
