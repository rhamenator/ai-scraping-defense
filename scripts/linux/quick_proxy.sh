#!/usr/bin/env bash
# Quick setup for Apache or Nginx reverse proxy deployment
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

# OS guard: Linux only
if [ "$(uname -s)" != "Linux" ]; then
  echo "Unsupported OS: $(uname -s). This entrypoint supports Linux only." >&2
  echo "Use scripts/macos/*.zsh on macOS or scripts/windows/*.ps1 on Windows." >&2
  exit 1
fi

# Helpers
# shellcheck source=scripts/linux/lib.sh
source "$SCRIPT_DIR/lib.sh"

echo "=== AI Scraping Defense: Proxy Quick Start ==="

if [ ! -f .env ]; then
  cp sample.env .env
  echo "Created .env from sample.env"
fi

PROXY=${1:-nginx}

if [ -z "${NO_NEW_PRIVILEGES:-}" ]; then
  if $(docker_ctx) run --rm --security-opt no-new-privileges:true alpine:3.20 true >/dev/null 2>&1; then
    export NO_NEW_PRIVILEGES=true
  else
    export NO_NEW_PRIVILEGES=false
    echo "Runtime does not support no-new-privileges:true; setting NO_NEW_PRIVILEGES=false."
  fi
fi

env_file_value() {
  local key="$1"
  awk -F= -v k="$key" '$1==k { print substr($0, index($0, "=") + 1); exit }' .env
}

port_in_use() {
  local port="$1"
  ss -ltn "( sport = :${port} )" 2>/dev/null | tail -n +2 | grep -q .
}

nginx_owns_host_port() {
  local port="$1"
  local container_port="$2"
  local mapped_ports

  mapped_ports=$($(docker_ctx) ps --filter name=^/nginx_proxy$ --format '{{.Ports}}' 2>/dev/null || true)
  echo "$mapped_ports" | grep -Eq "(^|, )[^,]*:${port}->${container_port}/tcp"
}

if [ "$PROXY" = "nginx" ]; then
  desired_http_port="${NGINX_HTTP_PORT:-$(env_file_value NGINX_HTTP_PORT)}"
  desired_https_port="${NGINX_HTTPS_PORT:-$(env_file_value NGINX_HTTPS_PORT)}"
  desired_http_port="${desired_http_port:-80}"
  desired_https_port="${desired_https_port:-443}"

  if port_in_use "$desired_http_port" && ! nginx_owns_host_port "$desired_http_port" 80; then
    for candidate in 8088 8081 18080; do
      if ! port_in_use "$candidate"; then
        export NGINX_HTTP_PORT="$candidate"
        echo "Port ${desired_http_port} is in use; using NGINX_HTTP_PORT=${candidate} for this run."
        break
      fi
    done
  fi

  if port_in_use "$desired_https_port" && ! nginx_owns_host_port "$desired_https_port" 443; then
    for candidate in 8443 9443 18443; do
      if ! port_in_use "$candidate"; then
        export NGINX_HTTPS_PORT="$candidate"
        echo "Port ${desired_https_port} is in use; using NGINX_HTTPS_PORT=${candidate} for this run."
        break
      fi
    done
  fi
fi

case "$PROXY" in
  apache)
    echo "Launching stack with Apache reverse proxy..."
    $(compose) up -d apache_proxy
    ;;
  nginx)
    echo "Launching stack with Nginx reverse proxy..."
    $(compose) up -d nginx_proxy
    ;;
  *)
    echo "Usage: $0 [apache|nginx]"
    exit 1
    ;;
esac

echo "Stack started with $PROXY reverse proxy."
