#!/bin/bash
# Quick setup script for local development
set -e

# Always operate from the directory where this script resides
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== AI Scraping Defense: Development Quickstart ==="

# Copy sample.env if .env doesn't exist
if [ ! -f .env ]; then
  cp sample.env .env
  echo "Created .env from sample.env"
fi

# Prepare local directories
bash ./setup_local_dirs.sh

# Generate local secrets
bash ./generate_secrets.sh

# Reset Python virtual environment (requires sudo for system packages)
sudo bash ./reset_venv.sh

# Run tests to ensure environment integrity
./.venv/bin/python test/run_all_tests.py

# Launch the stack with Docker Compose
docker-compose up --build -d

echo "Development environment is up and running!"
