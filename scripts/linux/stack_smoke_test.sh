#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

# shellcheck source=scripts/linux/lib.sh
source "$SCRIPT_DIR/lib.sh"

echo "=== Stack Smoke Test (Linux) ==="

assert_running_and_healthy() {
  local container="$1"
  local status health

  status=$($(docker_ctx) inspect -f '{{.State.Status}}' "$container" 2>/dev/null || true)
  if [ "$status" != "running" ]; then
    echo "[FAIL] $container is not running (status=$status)" >&2
    return 1
  fi

  health=$($(docker_ctx) inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container" 2>/dev/null || true)
  if [ "$health" != "none" ] && [ "$health" != "healthy" ]; then
    echo "[FAIL] $container health is not healthy (health=$health)" >&2
    return 1
  fi

  echo "[OK] $container is running (health=$health)"
}

for svc in postgres_markov_db redis_store admin_ui escalation_engine tarpit_api nginx_proxy; do
  assert_running_and_healthy "$svc"
done

http_port=$($(docker_ctx) inspect -f '{{(index (index .NetworkSettings.Ports "80/tcp") 0).HostPort}}' nginx_proxy)
https_port=$($(docker_ctx) inspect -f '{{(index (index .NetworkSettings.Ports "443/tcp") 0).HostPort}}' nginx_proxy)

curl -fsS "http://127.0.0.1:${http_port}/" >/dev/null
echo "[OK] nginx_proxy HTTP is reachable on port ${http_port}"

curl -kfsS "https://127.0.0.1:${https_port}/" >/dev/null
echo "[OK] nginx_proxy HTTPS is reachable on port ${https_port}"

$(docker_ctx) exec admin_ui curl -fsS "http://127.0.0.1:5002/observability/health" >/dev/null
echo "[OK] admin_ui health endpoint is reachable"

$(docker_ctx) exec tarpit_api curl -fsS "http://127.0.0.1:8001/health" >/dev/null
echo "[OK] tarpit_api health endpoint is reachable"

esc_health=$($(docker_ctx) exec escalation_engine curl -sS "http://127.0.0.1:8003/health")
if ! echo "$esc_health" | grep -Eq '"status":"(healthy|degraded)"'; then
  echo "[FAIL] escalation_engine health payload is unexpected: $esc_health" >&2
  exit 1
fi
echo "[OK] escalation_engine health payload is acceptable"

echo "Smoke test passed."
