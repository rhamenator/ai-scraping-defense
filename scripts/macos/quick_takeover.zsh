#!/usr/bin/env zsh
# Quick script to stop host web server and run stack on port 80
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

echo "=== AI Scraping Defense: Server Takeover ==="

# Ensure .env exists
if [ ! -f .env ]; then
  cp sample.env .env
  echo "Created .env from sample.env"
fi

PROXY=${1:-nginx}

if [[ -z "${NO_NEW_PRIVILEGES:-}" ]]; then
  if docker run --rm --security-opt no-new-privileges:true alpine:3.20 true >/dev/null 2>&1; then
    export NO_NEW_PRIVILEGES=true
  else
    export NO_NEW_PRIVILEGES=false
    echo "Runtime does not support no-new-privileges:true; setting NO_NEW_PRIVILEGES=false."
  fi
fi

if [[ "$(uname)" == "Darwin" ]]; then
  for svc in apachectl nginx; do
    if command -v $svc >/dev/null 2>&1; then
      echo "Stopping $svc service..."
      sudo $svc stop
    fi
  done
elif command -v systemctl >/dev/null 2>&1; then
  for svc in apache2 nginx; do
    if systemctl is-active --quiet "$svc"; then
      echo "Stopping $svc service..."
      if [ "$(id -u)" -eq 0 ]; then
        systemctl stop "$svc"
      else
        sudo systemctl stop "$svc"
      fi
    fi
  done
fi

case "$PROXY" in
  apache)
    echo "Launching stack with Apache on port 80..."
    APACHE_HTTP_PORT=80 $(compose) up -d apache_proxy
    ;;
  nginx)
    echo "Launching stack with Nginx on port 80..."
    $(compose) up -d nginx_proxy
    ;;
  *)
    echo "Usage: $0 [apache|nginx]"
    exit 1
    ;;
esac

echo "Stack is now serving on port 80 via $PROXY."
