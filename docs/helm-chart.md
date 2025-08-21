# Helm Chart (v9)

Services:
- `core`, `proxy`, `cloud_proxy`, `prompt_router` (enable/disable via values).
- Optional `redis` (off by default in production).
- Primary & canary Ingress (NGINX). The canary ingress is separate and controlled by weight.

Images:
- Provided via `images:` values. Workflows generate an overlay `values-images.yaml` and pass `-f` to Helm.

Values files:
- `helm/values-staging.yaml` (1 replica, light defaults)
- `helm/values-production.yaml` (scaled replicas, requests/limits, prod host)
- `helm/canary-values.yaml` (enables canary ingress annotations if your ingress class needs extras)
