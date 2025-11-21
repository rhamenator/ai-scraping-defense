# Promotion & Canary

Auto-Promotion:
- Trigger: Regression E2E succeeds on `main`.
- Job: `.github/workflows/promote-on-green.yml` → prod deploy via Helm (gated by `production` environment approval).

Manual Prod Deploy:
- Job: `.github/workflows/deploy-prod.yml` (manual or `v*` tags).

Canary:
- Chart ships `ai-scraping-defense` (primary) and `ai-scraping-defense-canary` ingress with NGINX canary annotations.
- Adjust traffic with `.github/workflows/canary-shift.yml` input `weight` (0–100).
- Setting `weight` to 0 disables the canary.
