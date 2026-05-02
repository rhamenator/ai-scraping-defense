#!/usr/bin/env bash
# Quick script to stop host web server and run stack on port 80
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

echo "=== AI Scraping Defense: Server Takeover ==="

# Ensure .env exists
if [ ! -f .env ]; then
  cp sample.env .env
  echo "Created .env from sample.env"
fi

PROXY=${1:-nginx}

# Detect runtime support for no-new-privileges; keep containers launchable on
# engines that reject no-new-privileges:true.
if [ -z "${NO_NEW_PRIVILEGES:-}" ]; then
  if $(docker_ctx) run --rm --security-opt no-new-privileges:true alpine:3.20 true >/dev/null 2>&1; then
    export NO_NEW_PRIVILEGES=true
  else
    export NO_NEW_PRIVILEGES=false
    echo "Runtime does not support no-new-privileges:true; setting NO_NEW_PRIVILEGES=false."
  fi
fi

# Snapshot host webserver config before takeover unless explicitly disabled.
if [ "${TAKEOVER_SNAPSHOT:-1}" = "1" ]; then
  echo "Creating pre-takeover host webserver snapshot..."
  bash "$SCRIPT_DIR/webserver_snapshot.sh"
fi

# Determine if sudo is needed for systemctl
if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  SUDO="sudo"
fi

if command -v systemctl >/dev/null 2>&1; then
  for svc in apache2 nginx; do
    if systemctl is-active --quiet "$svc"; then
      echo "Stopping $svc service..."
      $SUDO systemctl stop "$svc"
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
