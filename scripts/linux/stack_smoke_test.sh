#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

# shellcheck source=scripts/linux/lib.sh
source "$SCRIPT_DIR/lib.sh"

PROXY="nginx"

usage() {
  cat <<'USAGE'
Usage: scripts/linux/stack_smoke_test.sh [--proxy nginx|apache]
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --proxy)
      PROXY="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

echo "=== Stack Smoke Test (Linux / ${PROXY}) ==="

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

core_services=(postgres_markov_db redis_store admin_ui escalation_engine tarpit_api)
case "$PROXY" in
  nginx)
    proxy_container="nginx_proxy"
    ;;
  apache)
    proxy_container="apache_proxy"
    ;;
  *)
    echo "[FAIL] Unsupported proxy: ${PROXY}" >&2
    exit 2
    ;;
esac

for svc in "${core_services[@]}" "$proxy_container"; do
  assert_running_and_healthy "$svc"
done

http_port=$(
  $(docker_ctx) inspect -f '{{(index (index .NetworkSettings.Ports "80/tcp") 0).HostPort}}' "$proxy_container"
)

curl -fsS "http://127.0.0.1:${http_port}/" >/dev/null
echo "[OK] ${proxy_container} HTTP is reachable on port ${http_port}"

if [ "$PROXY" = "nginx" ]; then
  https_port=$(
    $(docker_ctx) inspect -f '{{(index (index .NetworkSettings.Ports "443/tcp") 0).HostPort}}' nginx_proxy
  )
  curl -kfsS "https://127.0.0.1:${https_port}/" >/dev/null
  echo "[OK] nginx_proxy HTTPS is reachable on port ${https_port}"
fi

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
