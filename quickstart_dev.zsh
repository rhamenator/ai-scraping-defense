#!/bin/zsh
# Quick setup script for local development on macOS
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== AI Scraping Defense: Development Quickstart ==="

if [ ! -f .env ]; then
  cp sample.env .env
  echo "Created .env from sample.env"
fi

./setup_local_dirs.zsh
./generate_secrets.zsh
./reset_venv.zsh
./.venv/bin/pip install -r requirements.txt -c constraints.txt
./.venv/bin/python scripts/validate_env.py
./.venv/bin/python test/run_all_tests.py
docker-compose up --build -d

echo "Development environment is up and running!"
