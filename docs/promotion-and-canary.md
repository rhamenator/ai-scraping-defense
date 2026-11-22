# Promotion & Canary

Auto-Promotion:
- Trigger: Regression E2E succeeds on `main`.
- Job: `.github/workflows/promote-on-green.yml` → prod deploy via Helm (gated by `production` environment approval).

Manual Prod Deploy:
- Job: `.github/workflows/deploy-prod.yml` (manual or `v*` tags).

Canary:
- Chart ships `ai-scraping-defense` (primary) and `ai-scraping-defense-canary` ingress with NGINX canary annotations.
- Adjust traffic with `.github/workflows/canary-shift.yml`, whose only input is `weight` (a whole number from 0 to 100). The job runs in the `production` environment, so it waits for that environment's required-reviewer approval and uses the cloud secrets stored there. The namespace (`production`) and the ingress (`ai-scraping-defense-canary`) are fixed in the workflow and cannot be chosen at dispatch time.
- Keep the service account behind `GCP_SERVICE_ACCOUNT` limited to annotating that one ingress (a namespaced Role with `get` and `patch` on that ingress name only) and store the GCP values as `production` environment secrets rather than repository secrets.
