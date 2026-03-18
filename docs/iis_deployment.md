# IIS Deployment Note

This repository is the Python-first stack and does not carry the primary, continuously updated IIS deployment path anymore.

## Use the Dedicated IIS/.NET Repository

For production IIS deployment guidance, use the `.NET` stack documentation in `ai-scraping-defense-iis`:

- `README.md`
- `docs/iis_deployment_guide.md`
- `docs/api_references.md`
- `docs/operator_runbook.md`

## Why This Change

Keeping full IIS runbooks in two repositories caused drift and contradictory instructions. IIS guidance is now maintained in one place to keep operations docs current and auditable.

## Scope Boundary

- This repository remains the canonical Python stack documentation source.
- IIS-first deployment and operator workflows are documented and versioned in the `.NET` stack.
