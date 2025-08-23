#!/bin/bash
# =============================================================================
#  stress_test.sh - run a simple k6 load test against the stack
#
#  Use only against infrastructure you own or have permission to test.
# =============================================================================
set -e

TARGET="${1:-http://localhost:8080}"
VUS="${VUS:-50}"
DURATION="${DURATION:-30s}"

echo "=== Running k6 stress test on $TARGET for $DURATION with $VUS VUs ==="

if ! command -v k6 >/dev/null; then
    echo "ERROR: k6 is not installed. Install from https://k6.io/ before running." >&2
    exit 1
fi

cat <<EOT > /tmp/k6_stress.js
import http from 'k6/http';
import { sleep } from 'k6';
export let options = {
  vus: $VUS,
  duration: '$DURATION',
};
export default function () {
  http.get('$TARGET');
  sleep(1);
}
EOT

k6 run /tmp/k6_stress.js
rm /tmp/k6_stress.js

echo "k6 stress test complete."
