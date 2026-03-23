# Python Dependency Refresh Plan

This document captures the March 2026 dependency triage for the Python stack.
It is intentionally focused on direct dependencies and operator-visible risk so
future refresh PRs can be scoped into small, reviewable batches.

## Scan Basis

- Scan date: 2026-03-22
- Repository inputs reviewed: `requirements.txt`, `requirements.lock`, and
  `requirements-kubernetes.txt` on `main`
- Index check used: `python -m pip list --outdated --format=json`

The local virtualenv scan reported 84 outdated packages in the active
environment:

- 26 major-version jumps
- 34 minor-version updates
- 24 patch-version updates

Because the local environment was not perfectly synchronized with the checked-in
lockfile, the staged plan below treats the repository-managed requirement files
as the source of truth for current versions and uses the index scan only to
identify newer available releases.

Many of the reported updates are transitive dependencies. The staged plan below
focuses first on the direct requirements owned by this repository.

## Low-Risk Refresh Candidates

These updates stay within the current major line or are otherwise good
candidates for an automated refresh PR with normal regression coverage.

### Patch-Level Direct Updates

- `cohere` `5.16.1 -> 5.20.7`
- `coverage` `7.13.1 -> 7.13.5`
- `joblib` `1.5.1 -> 1.5.3`
- `pip-tools` `7.5.2 -> 7.5.3`
- `pyasn1` `0.6.2 -> 0.6.3`
- `webauthn` `2.7.0 -> 2.7.1`

### Minor-Level Direct Updates

- `anthropic` `0.60.0 -> 0.86.0`
- `cbor2` `5.8.0 -> 5.9.0`
- `fastapi` `0.128.2 -> 0.135.1`
- `filelock` `3.20.3 -> 3.25.2`
- `geoip2` `5.1.0 -> 5.2.0`
- `google-genai` `1.27.0 -> 1.68.0`
- `maturin` `1.9.2 -> 1.12.6`
- `pytest-asyncio` `1.1.0 -> 1.3.0`
- `redis` `7.1.0 -> 7.3.0`
- `scikit-learn` `1.7.1 -> 1.8.0`
- `uvicorn` `0.40.0 -> 0.42.0`

### Low-Risk but Separate Batch

These are direct dependencies or infra-facing libraries but should be refreshed
in their own small PR because they influence deployment or infrastructure
paths:

- `kubernetes` is managed via `requirements-kubernetes.txt` as `kubernetes~=35.0`
  and should be reviewed there in coordination with cluster/API compatibility
- `pytest-asyncio` and other test-only updates if CI behavior changes

## Risky or Compatibility-Sensitive Upgrades

These upgrades either cross major versions, sit on critical framework seams, or
affect core ML/data paths that are likely to need compatibility work.

### Framework / Runtime Coordination

- `starlette` `0.50.0 -> 1.0.0`
  - FastAPI compatibility must be validated before moving to the 1.x line.
- `cachetools` currently resolves to `5.5.2` in `requirements.lock` even though
  `requirements.txt` already allows `cachetools~=7.0`
  - Align the lockfile and environments with the existing 7.x requirement, then
    verify TTL cache semantics and any custom wrappers.
- `tenacity` `8.5.0 -> 9.1.4`
  - Retry behavior and decorator signatures should be regression tested.

### AI and SDK Major Migrations

- `openai` `1.97.1 -> 2.29.0`
  - High-risk SDK migration for all provider adapters and request/response code.
- `mistralai` `1.9.3 -> 2.1.2`
  - Requires adapter contract validation and error-path checks.
- `transformers` `4.54.1 -> 5.3.0`
  - Major ML framework update; likely to affect tokenization and pipeline code.

### Data / Model Compatibility

- `datasets` `2.21.0 -> 4.8.3`
  - Large major-version jump despite permissive bounds; validate dataset loading,
    cache layout, and evaluation helpers.
- `numpy` `1.26.4 -> 2.4.3`
  - Major numerical stack migration; check compiled dependencies and model code.
- `pandas` `2.3.1 -> 3.0.1`
  - Expect deprecation removals and stricter dataframe behavior.
- `xgboost` `2.1.4 -> 3.2.0`
  - Validate model load/train compatibility and serialized artifact handling.

### Tooling Major Updates

- `pytest` `8.4.1 -> 9.0.2`
- `virtualenv` `20.36.1 -> 21.2.0`

`isort` is already aligned at `8.0.1` in `requirements.lock`, and `pyOpenSSL`
is already aligned at `26.0.0`, so they do not represent active backlog items.
These tooling/runtime jumps that remain are likely manageable, but they should
not be mixed into production dependency refreshes.

## Proposed Execution Plan

### Stage 1: Safe Automated Refresh

Open a narrow PR that updates the patch-level direct dependencies plus the
lowest-risk minor updates:

- `cohere`, `coverage`, `joblib`, `pip-tools`, `pyasn1`, `webauthn`
- `anthropic`, `cbor2`, `filelock`, `geoip2`, `google-genai`, `redis`,
  `uvicorn`

Validation:

- targeted unit tests for touched areas
- `python -m pytest`
- `pre-commit run --files ...`

### Stage 2: Framework and Data Refresh Within Current Major Lines

Refresh packages that are still same-major or bounded by current requirements
but touch application behavior more broadly:

- `fastapi`, `pytest-asyncio`, `scikit-learn`, `maturin`
- resolve the `cachetools` lockfile drift to the already-allowed 7.x line
- optionally `kubernetes` in a dedicated infra-focused PR

Validation:

- full Python test suite
- smoke checks for API startup and request handling
- any model-loading or training regressions that use these libraries

### Stage 3: Tooling-Only Major Updates

Move test and formatting toolchain changes into a separate maintenance PR:

- `pytest` 9
- `isort` 8
- `virtualenv` 21

Validation:

- lint/format hooks
- test discovery and async fixture behavior
- CI workflow compatibility

### Stage 4: Major Migration Workstreams

Split the highest-risk runtime migrations into dedicated PRs or short-lived
tracks with explicit compatibility testing:

- provider SDK migration: `openai` 2 and `mistralai` 2
- ML/data migration: `datasets` 4, `numpy` 2, `transformers` 5, `pandas` 3,
  `xgboost` 3
- framework seam migration: `starlette` 1, `cachetools` 7, `tenacity` 9

Each of these should include focused code archaeology, compatibility testing,
and release-note review before changing version bounds.

## Recommended Immediate Follow-Up

1. Open a Stage 1 dependency refresh PR limited to low-risk direct updates.
2. Keep `openai`, `mistralai`, `datasets`, `numpy`, `transformers`, `pandas`,
  and `xgboost` out of the first refresh batch.
3. Track `starlette` with FastAPI compatibility rather than updating it in
   isolation.
4. Re-run the outdated scan after Stage 1 to shrink the transitive backlog and
   reclassify any remaining gaps.
