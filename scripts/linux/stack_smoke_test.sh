#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

PROXY="nginx"

usage() {
  cat <<'USAGE'
Usage: scripts/linux/stack_smoke_test.sh [--proxy nginx|apache]
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --proxy)
      PROXY="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

PYTHON_BIN="./.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

exec "$PYTHON_BIN" scripts/installer_smoke_test.py --platform linux --proxy "$PROXY"
