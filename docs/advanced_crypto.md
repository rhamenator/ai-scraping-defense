# Advanced Cryptography Roadmap

This document captures the planned work for advanced cryptographic features
without changing runtime behavior in the current release.

## Post-Quantum Cryptography

Goal: evaluate post-quantum algorithms for key exchange and signatures in
environments where long-term confidentiality is required.

Suggested approach:

- Track NIST PQC standardization outcomes.
- Prototype in isolated services behind feature flags.
- Measure latency impact for TLS termination and token signing.

## Homomorphic Encryption

Goal: explore homomorphic techniques for sensitive computations (e.g., analytics)
without exposing raw data.

Suggested approach:

- Limit scope to offline analytics or reporting jobs.
- Benchmark library performance and memory overhead.
- Define acceptable workloads before enabling in production.

## Next Steps

- Define a minimal POC scope and evaluation criteria.
- Add targeted tests when experimental implementations are introduced.
