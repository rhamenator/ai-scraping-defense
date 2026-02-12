#!/usr/bin/env bash
# Start a Cloudflare Tunnel for local stack testing behind ISP port blocks.
#
# Modes:
# 1) Quick tunnel (no account linkage required):
#    ./scripts/linux/start_cloudflare_tunnel.sh
#    -> exposes the local proxy URL via a temporary *.trycloudflare.com URL.
#
# 2) Named tunnel (recommended for stable hostname):
#    CLOUDFLARE_TUNNEL_TOKEN=... ./scripts/linux/start_cloudflare_tunnel.sh
#    -> runs a named tunnel using the token from Cloudflare Zero Trust.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

NGINX_HTTP_PORT_DEFAULT="$(read_env_var "NGINX_HTTP_PORT")"
if [[ -z "$NGINX_HTTP_PORT_DEFAULT" ]]; then
  NGINX_HTTP_PORT_DEFAULT="80"
fi

TARGET_URL="${1:-${CLOUDFLARE_TUNNEL_TARGET_URL:-http://localhost:${NGINX_HTTP_PORT_DEFAULT}}}"
TUNNEL_TOKEN="${CLOUDFLARE_TUNNEL_TOKEN:-}"

echo "=== Cloudflare Tunnel Launcher ==="
echo "Repository root: $ROOT_DIR"
echo "Target URL:      $TARGET_URL"
echo

if [[ -n "$TUNNEL_TOKEN" ]]; then
  echo "Mode: named tunnel (token-based)"
  echo "Expected outcome: traffic reaches this stack through your configured Cloudflare hostname."
  echo
else
  echo "Mode: quick tunnel (temporary trycloudflare.com URL)"
  echo "Expected outcome: cloudflared prints a temporary public URL in the logs."
  echo
fi

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
  exec docker run --rm --network host cloudflare/cloudflared:latest \
    tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"
fi

exec docker run --rm --network host cloudflare/cloudflared:latest \
  tunnel --no-autoupdate --url "$TARGET_URL"
