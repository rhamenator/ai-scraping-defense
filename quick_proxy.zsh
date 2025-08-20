#!/bin/zsh
# Quick setup for Apache or Nginx reverse proxy deployment
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== AI Scraping Defense: Proxy Quick Start ==="

if [ ! -f .env ]; then
  cp sample.env .env
  echo "Created .env from sample.env"
fi

PROXY=${1:-nginx}

case "$PROXY" in
  apache)
    echo "Launching stack with Apache reverse proxy..."
    docker compose up -d apache_proxy
    ;;
  nginx)
    echo "Launching stack with Nginx reverse proxy..."
    docker compose up -d nginx_proxy
    ;;
  *)
    echo "Usage: $0 [apache|nginx]"
    exit 1
    ;;
 esac

echo "Stack started with $PROXY reverse proxy."
