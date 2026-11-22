# Keeping the OWASP Core Rule Set up to date in Kubernetes

The `owasp-crs-fetcher` CronJob downloads a pinned OWASP CRS release, verifies it, stages and installs it on a shared
volume, and asks Kubernetes to roll the Nginx Deployment so its pods start with the new rules. It ships **suspended**
because it only helps once your Nginx can actually run ModSecurity.

## What you need first

1. **A ModSecurity-capable Nginx image.** The stock OpenResty image in `kubernetes/nginx-deployment.yaml` has no
   ModSecurity, so CRS rules cannot take effect on it. Switch the `nginx-proxy` Deployment to an image that includes the
   ModSecurity module and loads it (the Docker/compose configuration in `nginx/nginx.default.conf` shows the directives).
2. **A `modsecurity.conf` that includes the CRS** from the mount path used below:
   ```
   Include /etc/nginx/modsecurity/crs/crs-setup.conf
   Include /etc/nginx/modsecurity/crs/rules/*.conf
   ```
3. **A ReadWriteMany volume** (or a single Nginx replica on the job's node) for the rules.

## The fetcher image needs the Kubernetes client

`WAF_RELOAD_MODE=kubernetes` talks to the Kubernetes API, and the project's standard image installs only
`requirements.txt`, which does not include the Kubernetes client (`requirements-kubernetes.txt` does). Without it the job
downloads and verifies the rules, cannot ask Kubernetes to restart Nginx, and restores the previous rules, with a log
line saying the client library is missing. Build a small derived image and point the CronJob at it:

```dockerfile
FROM your-registry/ai-scraping-defense:latest
RUN pip install --no-cache-dir "kubernetes~=35.0"
```

(Use the same version range as `requirements-kubernetes.txt`.) Or set `WAF_RELOAD_MODE=none` and roll the Nginx
Deployment yourself after each run.

## Turn it on

```bash
kubectl apply -f kubernetes/optional-waf-crs/waf-rules-pvc.yaml
kubectl apply -f kubernetes/waf-rules-fetcher-rbac.yaml
kubectl -n ai-defense patch deployment nginx-proxy --patch-file kubernetes/optional-waf-crs/nginx-waf-volume.patch.yaml
kubectl apply -f kubernetes/waf-rules-fetcher-cronjob.yaml
kubectl -n ai-defense patch cronjob owasp-crs-fetcher -p '{"spec":{"suspend":false}}'
# Try it once without waiting for 03:00:
kubectl -n ai-defense create job --from=cronjob/owasp-crs-fetcher crs-first-run
kubectl -n ai-defense logs job/crs-first-run
```

A good run logs `OWASP CRS successfully installed` and `Requested a rolling restart of Deployment 'nginx-proxy'`.

## Moving to a newer CRS release

The job is pinned on purpose: an update is a decision, not something a download server can do to you. To move to a new
release, change `CRS_DOWNLOAD_URL` and `CRS_SHA256` together in `waf-rules-fetcher-cronjob.yaml`:

```bash
curl -sSLo crs.tar.gz https://codeload.github.com/coreruleset/coreruleset/tar.gz/refs/tags/<tag>
sha256sum crs.tar.gz        # put this in CRS_SHA256; read the release notes before you do
```

The URL must be the final download URL (redirects are refused), which is why it points at `codeload.github.com` and not
at the `github.com/.../archive/...` link that redirects there. The job then installs only if the download matches the pin.

## If something goes wrong

- **The job fails and logs a reason** (digest mismatch, size limit, refused directive, no rolling restart): nothing was
  changed, or the previous rules were restored. The previous generation is also kept as `rules.previous` on the volume.
- **The restart was accepted but the new pods are unhealthy** (for example, a rule the engine will not load): Kubernetes
  keeps the old pods serving while the rollout is stuck. `kubectl rollout undo` will not fix it, because the rules live on
  the volume and not in the image. Restore the previous generation (rules and setup file together, so the restart loads a consistent set) from a pod that mounts the volume
  (`mv /waf/rules /waf/rules.bad && mv /waf/rules.previous /waf/rules && mv /waf/crs-setup.conf.previous /waf/crs-setup.conf`), then run
  `kubectl -n ai-defense rollout restart deployment/nginx-proxy`.
- **You want to look before it goes live:** set `WAF_RELOAD_MODE` to `none` in the CronJob. It then installs the rules
  and leaves the restart to you.
