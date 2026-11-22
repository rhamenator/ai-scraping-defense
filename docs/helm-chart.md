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

## TLS for the ingress

`helm/values-production.yaml` sets `ingress.requireTLS: true` and a `tls` entry. With `requireTLS` the chart fails to
render unless every `ingress.hosts[].host` appears under an `ingress.tls[]` entry that names a `secretName`, so a
production install cannot serve plain HTTP by accident. When `tls` is set and `className` is `nginx`, the chart adds the
`ssl-redirect` and `force-ssl-redirect` annotations (HTTP is redirected to HTTPS; ingress-nginx's HSTS default then applies).
Replace `prod-yourdomain.example.com` with your host, and either create the secret
(`kubectl create secret tls asd-prod-tls --cert=... --key=...`) or name a cert-manager issuer in `ingress.annotations`.
`scripts/check_helm_tls_policy.sh` checks this in CI. Setting `requireTLS: false` is possible and is your call; staging and
the sample values leave it off.
