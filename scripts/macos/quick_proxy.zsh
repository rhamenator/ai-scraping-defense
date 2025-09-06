#!/usr/bin/env zsh
# Quick setup for Apache or Nginx reverse proxy deployment
set -e
set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
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
