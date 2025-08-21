# Environments & PR Previews

Create **staging** and **production** in Settings → Environments.
- `staging`: set `STAGING_BASE_URL`, plus GCP secrets.
- `production`: add required reviewers; set `PROD_BASE_URL`, plus GCP secrets.

DNS:
- `staging.example.com` → ingress LB
- `*.staging.example.com` → same LB (for PR previews)

PR Previews:
- Tag images as `pr-<num>-<sha>`, namespace `pr-<num>`, helm release `ai-scraping-defense-pr-<num>`.
- Host `https://pr-<num>.<staging-domain>/`, commented on the PR; namespace deleted on close.
