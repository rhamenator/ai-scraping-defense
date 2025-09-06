#!/usr/bin/env zsh
# Quick setup script for local development on macOS
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
$(compose) up --build -d

echo "Development environment is up and running!"
