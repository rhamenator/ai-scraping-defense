#!/bin/bash
# Quick setup script for local development
set -e

# Warn if not running as root on Linux/macOS
if [ "$(id -u)" -ne 0 ]; then
  echo "WARNING: It's recommended to run this script with sudo on Linux/macOS" >&2
fi

# Always operate from the repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "=== AI Scraping Defense: Development Quickstart ==="

# Copy sample.env if .env doesn't exist
if [ ! -f .env ]; then
  cp sample.env .env
  echo "Created .env from sample.env"
fi

# Prepare local directories
bash "$SCRIPT_DIR/setup_local_dirs.sh"

# Generate local secrets
bash "$SCRIPT_DIR/generate_secrets.sh"

# Reset Python virtual environment (requires sudo for system packages)
sudo bash "$SCRIPT_DIR/reset_venv.sh"

# Install Python requirements with constraints
./.venv/bin/pip install -r requirements.txt -c constraints.txt

# Validate .env configuration
./.venv/bin/python scripts/validate_env.py

# Run tests to ensure environment integrity
./.venv/bin/python test/run_all_tests.py

# Launch the stack with Docker Compose
docker-compose up --build -d

echo "Development environment is up and running!"
