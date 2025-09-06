#!/usr/bin/env bash
# Quick setup for IIS deployment on Windows using WSL or Git Bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "=== AI Scraping Defense: IIS Quick Start ==="

if [ ! -f .env ]; then
  cp sample.env .env
  echo "Created .env from sample.env"
fi

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SCRIPT_DIR/../iis/start_services.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SCRIPT_DIR/../iis/configure_proxy.ps1"

echo "IIS deployment is ready."
