#!/bin/zsh
# Quick setup script for local development on macOS
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "=== AI Scraping Defense: Development Quickstart ==="

if [ ! -f .env ]; then
  cp sample.env .env
  echo "Created .env from sample.env"
fi

"$SCRIPT_DIR/setup_local_dirs.zsh"
"$SCRIPT_DIR/generate_secrets.zsh"
"$SCRIPT_DIR/reset_venv.zsh"
./.venv/bin/pip install -r requirements.txt -c constraints.txt
./.venv/bin/python scripts/validate_env.py
./.venv/bin/python test/run_all_tests.py
docker-compose up --build -d

echo "Development environment is up and running!"
