#!/usr/bin/env bash
# Checks the production Helm TLS policy (#1915): the production values must render an Ingress with a tls entry and an
# HTTP->HTTPS redirect, the chart must refuse to render production values without TLS, and an operator's own redirect
# annotations must win over the chart's defaults.
# Usage: scripts/check_helm_tls_policy.sh   (HELM="docker run --rm -v $PWD/helm:/h -w /h alpine/helm:3.16.4" to use a container)
set -u
cd "$(dirname "$0")/.." || exit 1
HELM_CMD=${HELM:-helm}
CHART=helm/ai-scraping-defense-v9
VALUES=helm/values-production.yaml
if [ -n "${HELM:-}" ]; then
  CHART=ai-scraping-defense-v9
  VALUES=values-production.yaml
fi
fail=0

check() { # check <description> <exit status of the condition>
  if [ "$2" -eq 0 ]; then
    echo "ok   $1"
  else
    echo "FAIL $1"
    fail=1
  fi
}

render() { $HELM_CMD template x "$CHART" -f "$VALUES" "$@" 2>&1; }

# rejected <exit status of render> <render output>: succeeds when the render failed because of the TLS policy
rejected() { [ "$1" -ne 0 ] && grep -q "requireTLS" <<<"$2"; }

out=$(render)
check "production values render" $?
grep -q "secretName:" <<<"$out"
check "production ingress has a TLS secret" $?
grep -q 'force-ssl-redirect: "true"' <<<"$out"
check "production ingress redirects HTTP to HTTPS" $?

out=$(render --set-json 'ingress.tls=[]')
rejected $? "$out"
check "empty tls is rejected" $?

out=$(render --set-json 'ingress.tls=[{"hosts":["prod-yourdomain.example.com"]}]')
rejected $? "$out"
check "tls entry without a secretName is rejected" $?

out=$(render --set-json 'ingress.tls=[{"secretName":"s","hosts":["elsewhere.example.com"]}]')
rejected $? "$out"
check "a host outside every tls entry is rejected" $?

out=$(render --set-json 'ingress.annotations={"nginx.ingress.kubernetes.io/force-ssl-redirect":"false"}')
grep -q 'force-ssl-redirect: "false"' <<<"$out"
check "an operator's own redirect annotation wins over the default" $?

exit $fail
