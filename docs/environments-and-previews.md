# Environments & PR Previews

Create **staging** and **production** in Settings → Environments.
- `staging`: set `STAGING_BASE_URL`, plus GCP secrets.
- `production`: add required reviewers; set `PROD_BASE_URL`, plus GCP secrets.
- `preview`: use the `Regression E2E` workflow `base_url` input with the
  preview URL you want to exercise. Preview runs do not infer a URL from
  secrets automatically.

DNS:
- `staging.example.com` → ingress LB
- `*.staging.example.com` → same LB (for PR previews)

PR Previews:
- Tag images as `pr-<num>-<sha>`, namespace `pr-<num>`, helm release `ai-scraping-defense-pr-<num>`.
- Host `https://pr-<num>.<staging-domain>/`, commented on the PR; namespace deleted on close.

Regression E2E target resolution:

- `workflow_dispatch` with `base_url` set: uses that explicit URL
- `environment=staging` or blank: uses `STAGING_BASE_URL`
- `environment=production`: uses `PROD_BASE_URL`
- `environment=preview`: requires explicit `base_url`
