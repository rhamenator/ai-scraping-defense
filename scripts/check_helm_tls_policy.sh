#!/usr/bin/env bash
# Checks the production Helm TLS policy (#1915): the production values must render an Ingress with a tls entry and an
# HTTP->HTTPS redirect, and the chart must refuse to render production values without TLS.
# Usage: scripts/check_helm_tls_policy.sh   (HELM="docker run --rm -v $PWD/helm:/h -w /h alpine/helm:3.16.4" to use a container)
set -u
cd "$(dirname "$0")/.."
HELM_CMD=${HELM:-helm}
CHART=helm/ai-scraping-defense-v9
VALUES=helm/values-production.yaml
if [ -n "${HELM:-}" ]; then CHART=ai-scraping-defense-v9; VALUES=values-production.yaml; fi
fail=0
check() { if [ "$2" = ok ]; then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi; }
render() { $HELM_CMD template x "$CHART" -f "$VALUES" "$@" 2>&1; }

out=$(render); rc=$?
[ $rc -eq 0 ] && check "production values render" ok || check "production values render" no
echo "$out" | grep -q "secretName:" && check "production ingress has a TLS secret" ok || check "production ingress has a TLS secret" no
echo "$out" | grep -q 'force-ssl-redirect: "true"' && check "production ingress redirects HTTP to HTTPS" ok || check "production ingress redirects HTTP to HTTPS" no

out=$(render --set-json 'ingress.tls=[]'); rc=$?
{ [ $rc -ne 0 ] && echo "$out" | grep -q "requireTLS"; } && check "empty tls is rejected" ok || check "empty tls is rejected" no
out=$(render --set-json 'ingress.tls=[{"hosts":["prod-yourdomain.example.com"]}]'); rc=$?
{ [ $rc -ne 0 ] && echo "$out" | grep -q "requireTLS"; } && check "tls entry without a secretName is rejected" ok || check "tls entry without a secretName is rejected" no
out=$(render --set-json 'ingress.tls=[{"secretName":"s","hosts":["elsewhere.example.com"]}]'); rc=$?
{ [ $rc -ne 0 ] && echo "$out" | grep -q "requireTLS"; } && check "a host outside every tls entry is rejected" ok || check "a host outside every tls entry is rejected" no
exit $fail
