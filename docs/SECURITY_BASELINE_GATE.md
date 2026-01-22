# Security Baseline Gate

The `security-controls` workflow is the single CI security baseline gate. It
runs on pull requests and mainline pushes and must be green before merge.

## What runs in the gate

- `scripts/security/run_static_security_checks.py`
- `bandit -q -r src`
- Targeted tests:
  - `test/test_security_baselines.py`
  - `test/test_security_middleware.py`
  - `test/test_security_inventory.py`
- `pip-audit`
- Trivy filesystem scan (container-scan job)
- Trivy config scan (compose-config-scan job)

Optional:
- `kubernetes-dependency-audit` runs only on manual dispatch with
  `audit_kubernetes=true`.

## Expected outputs

- Exit code `0` for all steps in `python-security`.
- Trivy jobs complete and report findings in the workflow logs.
- `pip-audit` completes without unresolved dependency errors.

## Failure handling

- Non-zero exit codes fail the workflow and block merge.
- Trivy findings do not fail the job by default (exit-code set to `0`); treat
  findings as follow-up issues if needed.
- If baseline checks fail, fix the underlying issue or update the baseline
  (e.g., security hardening config) and re-run the workflow.

## Deep scan scripts

The `scripts/*/security_scan.*` scripts are designed for manual, host-level
security testing and are not run inside CI.
