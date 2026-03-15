#!/usr/bin/env zsh
# Start a Cloudflare Tunnel for local stack testing behind ISP port blocks.
#
# Usage:
#   ./scripts/macos/start_cloudflare_tunnel.zsh
#   CLOUDFLARE_TUNNEL_TOKEN=... ./scripts/macos/start_cloudflare_tunnel.zsh
#   CLOUDFLARE_TUNNEL_TARGET_URL=http://localhost:8080 ./scripts/macos/start_cloudflare_tunnel.zsh

set -e
set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

read_env_var() {
  local key="$1"
  local env_file="${2:-.env}"
  if [[ ! -f "$env_file" ]]; then
    return 0
  fi
  local line
  line="$(grep -E "^${key}=" "$env_file" | tail -n1 || true)"
  line="${line#*=}"
  line="${line//$'\r'/}"
  printf "%s" "$line"
}

docker_origin_url() {
  local target="$1"
  target="${target/http:\/\/localhost:/http:\/\/host.docker.internal:}"
  target="${target/https:\/\/localhost:/https:\/\/host.docker.internal:}"
  printf "%s" "$target"
}

NGINX_HTTP_PORT_DEFAULT="$(read_env_var "NGINX_HTTP_PORT")"
if [[ -z "$NGINX_HTTP_PORT_DEFAULT" ]]; then
  NGINX_HTTP_PORT_DEFAULT="80"
fi

if [[ "${1:-}" != "" ]]; then
  TARGET_URL="$1"
else
  TARGET_URL="${CLOUDFLARE_TUNNEL_TARGET_URL:-http://localhost:${NGINX_HTTP_PORT_DEFAULT}}"
fi
TUNNEL_TOKEN="${CLOUDFLARE_TUNNEL_TOKEN:-}"

echo "=== Cloudflare Tunnel Launcher (macOS) ==="
echo "Repository root: $ROOT_DIR"
echo "Target URL:      $TARGET_URL"
echo

if [[ -n "$TUNNEL_TOKEN" ]]; then
  echo "Mode: named tunnel (token-based)"
else
  echo "Mode: quick tunnel (temporary trycloudflare.com URL)"
fi
echo

if command -v cloudflared >/dev/null 2>&1; then
  if [[ -n "$TUNNEL_TOKEN" ]]; then
    exec cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"
  fi
  exec cloudflared tunnel --no-autoupdate --url "$TARGET_URL"
fi

echo "cloudflared binary not found; attempting Docker fallback..."

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: neither cloudflared nor docker is available." >&2
  echo "Install cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" >&2
  exit 1
fi

if [[ -n "$TUNNEL_TOKEN" ]]; then
  exec docker run --rm cloudflare/cloudflared:latest \
    tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"
fi

DOCKER_TARGET_URL="$(docker_origin_url "$TARGET_URL")"
exec docker run --rm cloudflare/cloudflared:latest \
  tunnel --no-autoupdate --url "$DOCKER_TARGET_URL"
