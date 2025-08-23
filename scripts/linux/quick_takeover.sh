#!/bin/bash
# Quick script to stop host web server and run stack on port 80
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "=== AI Scraping Defense: Server Takeover ==="

# Ensure .env exists
if [ ! -f .env ]; then
  cp sample.env .env
  echo "Created .env from sample.env"
fi

PROXY=${1:-nginx}

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
    APACHE_HTTP_PORT=80 docker compose up -d apache_proxy
    ;;
  nginx)
    echo "Launching stack with Nginx on port 80..."
    docker compose up -d nginx_proxy
    ;;
  *)
    echo "Usage: $0 [apache|nginx]"
    exit 1
    ;;
fi

echo "Stack is now serving on port 80 via $PROXY."

