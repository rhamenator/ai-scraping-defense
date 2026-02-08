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
