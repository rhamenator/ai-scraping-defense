#!/usr/bin/env zsh
# Quick setup for Apache or Nginx reverse proxy deployment
set -e
set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Unsupported OS: $(uname -s). This entrypoint supports macOS only." 1>&2
  echo "Use scripts/linux/*.sh on Linux or scripts/windows/*.ps1 on Windows." 1>&2
  exit 1
fi

source "$SCRIPT_DIR/lib.zsh"

echo "=== AI Scraping Defense: Proxy Quick Start ==="

if [ ! -f .env ]; then
  cp sample.env .env
  echo "Created .env from sample.env"
fi

PROXY=${1:-nginx}

ensure_no_new_privileges_env

if [[ "$PROXY" == "nginx" ]]; then
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
